"""Deposits and move-out settlement rules."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from billing.models import MeterReading
from operations.models import Deposit, MoveOut, MoveOutItem
from property.models import Lease

DEFAULT_ITEMS = [
    MoveOutItem.ITEM_DOOR,
    MoveOutItem.ITEM_SHUTTER,
    MoveOutItem.ITEM_LIGHTS,
    MoveOutItem.ITEM_FLOOR,
    MoveOutItem.ITEM_METER,
]


def held_deposit_total(lease) -> Decimal:
    value = sum(
        (
            deposit.amount_received
            for deposit in lease.deposits.filter(
                status__in=[Deposit.STATUS_HELD, Deposit.STATUS_PARTLY_REFUNDED]
            )
        ),
        Decimal("0.00"),
    )
    return value


def record_deposit(lease, amount_received, received_date, payment=None):
    amount = Decimal(str(amount_received or "0"))
    if amount <= 0:
        raise ValidationError("Enter a deposit amount greater than zero.")
    return Deposit.objects.create(
        lease=lease,
        amount_received=amount,
        received_date=received_date,
        payment=payment,
        status=Deposit.STATUS_HELD,
    )


def compute_move_out(move_out: MoveOut, save=True) -> MoveOut:
    if move_out.status == MoveOut.STATUS_SETTLED:
        return move_out
    lease = move_out.lease
    damages = sum(
        (item.damage_cost for item in move_out.items.all()), Decimal("0.00")
    )
    deposit_held = held_deposit_total(lease)
    arrears = lease.tenant.balance_due
    refund = deposit_held - arrears - damages
    if refund < 0:
        refund = Decimal("0.00")

    move_out.damages_amount = damages
    move_out.deposit_held = deposit_held
    move_out.arrears_at_exit = arrears
    move_out.refund_amount = refund
    if save:
        move_out.save(
            update_fields=[
                "damages_amount",
                "deposit_held",
                "arrears_at_exit",
                "refund_amount",
                "updated_at",
            ]
        )
    return move_out


@transaction.atomic
def create_move_out(lease: Lease, move_out_date, notice_date=None, notes=""):
    if lease.move_outs.filter(status=MoveOut.STATUS_PLANNED).exists():
        raise ValidationError("This lease already has a planned move-out.")
    move_out = MoveOut.objects.create(
        lease=lease,
        notice_date=notice_date,
        move_out_date=move_out_date,
        settlement_notes=notes,
        status=MoveOut.STATUS_PLANNED,
    )
    for item in DEFAULT_ITEMS:
        MoveOutItem.objects.create(
            move_out=move_out, item=item, condition="ok", damage_cost=Decimal("0.00")
        )
    compute_move_out(move_out)
    return move_out


@transaction.atomic
def settle_move_out(move_out: MoveOut, user=None):
    if move_out.status == MoveOut.STATUS_SETTLED:
        return move_out
    compute_move_out(move_out)

    if move_out.refund_amount <= 0:
        deposit_status = Deposit.STATUS_FORFEITED
    elif move_out.refund_amount >= move_out.deposit_held:
        deposit_status = Deposit.STATUS_REFUNDED
    else:
        deposit_status = Deposit.STATUS_PARTLY_REFUNDED

    for deposit in move_out.lease.deposits.filter(
        status__in=[Deposit.STATUS_HELD, Deposit.STATUS_PARTLY_REFUNDED]
    ):
        deposit.status = deposit_status
        deposit.save(update_fields=["status", "updated_at"])

    move_out.status = MoveOut.STATUS_SETTLED
    move_out.save(update_fields=["status", "updated_at"])

    lease = move_out.lease
    if lease.status != Lease.STATUS_TERMINATED:
        lease.status = Lease.STATUS_TERMINATED
        lease.terminated_on = move_out.move_out_date
        lease.termination_reason = "Move-out"
        lease.save(
            update_fields=[
                "status",
                "terminated_on",
                "termination_reason",
                "updated_at",
            ]
        )
    return move_out


def record_final_readings(lease, move_out_date, readings):
    """readings: list of (utility_type, value or None)."""
    for utility_type, value in readings:
        if value in (None, ""):
            continue
        existing = MeterReading.objects.filter(
            unit=lease.unit,
            utility_type=utility_type,
            reading_date=move_out_date,
        ).first()
        if existing and existing.invoice_line_id:
            raise ValidationError(
                f"The {utility_type.name} reading for this date is already invoiced."
            )
        previous = (
            MeterReading.objects.filter(
                unit=lease.unit,
                utility_type=utility_type,
                reading_date__lt=move_out_date,
            )
            .exclude(pk=existing.pk if existing else None)
            .order_by("-reading_date", "-id")
            .first()
        )
        if previous and Decimal(str(value)) < previous.reading_value:
            raise ValidationError(
                f"The {utility_type.name} reading cannot be below {previous.reading_value}."
            )
        reading = existing or MeterReading(
            unit=lease.unit,
            utility_type=utility_type,
            reading_date=move_out_date,
        )
        reading.reading_value = Decimal(str(value))
        reading.full_clean()
        reading.save()
