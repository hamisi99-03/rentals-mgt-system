"""Invoice generation: escalation, 30-day proration, charges, utilities and VAT.

Money rules confirmed for Phase 3:
- partial months use a fixed 30-day month
- monthly lease charges prorate, quarterly and once charges bill in full
- rent and utility lines follow the tenant VAT flag; service/other lines follow
  ChargeType.vat_applicable
- missed escalations are applied compounding up to the invoice period start
- active and expired leases that overlap the period are billed; drafts and
  terminated leases are not
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from billing.models import (
    ChargeType,
    Invoice,
    InvoiceLine,
    LeaseCharge,
    MeterReading,
)
from core.models import NumberSequence, Settings, get_current_user
from core.numbering import next_document_number
from property.models import Lease, LeaseRentHistory

MONEY = Decimal("0.01")
HUNDRED = Decimal("100")
PRORATION_DAYS = Decimal("30")


def money(value) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def parse_period(value: str):
    try:
        parsed = datetime.strptime(str(value).strip(), "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise ValueError("Period must be in YYYY-MM format.") from exc
    return month_bounds(parsed.year, parsed.month)


def period_label(period_start) -> str:
    return period_start.strftime("%b %Y")


def default_due_date(period_start, settings_obj=None) -> date:
    settings_obj = settings_obj or Settings.load()
    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    day = min(settings_obj.invoice_due_day, last_day)
    return date(period_start.year, period_start.month, day)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def period_days(period_start, period_end) -> int:
    return (period_end - period_start).days + 1


def active_days(start, end, period_start, period_end) -> int:
    first = max(start, period_start)
    last = min(end, period_end)
    if last < first:
        return 0
    return (last - first).days + 1


def prorated_amount(amount: Decimal, days: int, days_in_period: int) -> Decimal:
    amount = Decimal(amount)
    if days <= 0:
        return Decimal("0.00")
    if days >= days_in_period:
        return money(amount)
    capped = min(days, int(PRORATION_DAYS))
    return money(amount * Decimal(capped) / PRORATION_DAYS)


def simulate_escalations(lease: Lease, period_start):
    """Return (rent after due steps, list of steps, next escalation date)."""
    rent = Decimal(lease.monthly_rent)
    next_date = lease.next_escalation_date
    interval = lease.escalation_interval_months
    steps = []
    guard = 0

    if lease.escalation_type == Lease.ESCALATION_NONE or not interval or interval < 1:
        return rent, steps, next_date

    while next_date and next_date <= period_start and guard < 120:
        old_rent = rent
        if lease.escalation_type == Lease.ESCALATION_PERCENT:
            rent = money(rent * (HUNDRED + Decimal(lease.escalation_value)) / HUNDRED)
        else:
            rent = money(rent + Decimal(lease.escalation_value))
        steps.append((next_date, old_rent, rent))
        next_date = add_months(next_date, interval)
        guard += 1

    return rent, steps, next_date


@dataclass
class LineSpec:
    kind: str
    description: str
    amount: Decimal
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    charge_type: ChargeType | None = None
    reading: MeterReading | None = None
    vat_amount: Decimal = Decimal("0.00")


def _charge_amount(charge: LeaseCharge, lease: Lease, period_start, period_end, days_in_period):
    if not charge.is_active:
        return None
    if charge.start_date > period_end:
        return None
    if charge.end_date and charge.end_date < period_start:
        return None

    if charge.frequency == LeaseCharge.FREQUENCY_MONTHLY:
        first = max(charge.start_date, lease.start_date, period_start)
        last = min(charge.end_date or period_end, lease.end_date, period_end)
        days = (last - first).days + 1 if last >= first else 0
        return prorated_amount(charge.amount, days, days_in_period), days

    if charge.frequency == LeaseCharge.FREQUENCY_QUARTERLY:
        months_since = (
            (period_start.year - charge.start_date.year) * 12
            + (period_start.month - charge.start_date.month)
        )
        if months_since < 0 or months_since % 3 != 0:
            return None
        return money(charge.amount), None

    if charge.frequency == LeaseCharge.FREQUENCY_ONCE:
        if period_start <= charge.start_date <= period_end:
            return money(charge.amount), None
        return None
    return None


def _line_vat(kind, charge_type, amount, vat_enabled, tenant_vat, vat_rate):
    if not vat_enabled or not tenant_vat:
        return Decimal("0.00")
    if kind in (InvoiceLine.KIND_RENT, InvoiceLine.KIND_UTILITY):
        return money(amount * vat_rate / HUNDRED)
    if kind in (InvoiceLine.KIND_SERVICE, InvoiceLine.KIND_OTHER):
        if charge_type and charge_type.vat_applicable:
            return money(amount * vat_rate / HUNDRED)
    return Decimal("0.00")


def build_line_specs(lease: Lease, rent: Decimal, period_start, period_end, settings_obj):
    days_in_period = period_days(period_start, period_end)
    lease_days = active_days(lease.start_date, lease.end_date, period_start, period_end)
    rent_amount = prorated_amount(rent, lease_days, days_in_period)
    rent_description = f"Rent - {period_label(period_start)}"
    if lease_days < days_in_period:
        rent_description += " (part month)"

    vat_enabled = settings_obj.vat_enabled
    tenant_vat = lease.tenant.vat_applicable
    vat_rate = Decimal(settings_obj.vat_rate)

    specs = [
        LineSpec(
            kind=InvoiceLine.KIND_RENT,
            description=rent_description,
            amount=rent_amount,
            unit_price=rent_amount,
        )
    ]

    charges = lease.charges.filter(is_active=True).select_related("charge_type")
    for charge in charges:
        result = _charge_amount(
            charge, lease, period_start, period_end, days_in_period
        )
        if result is None:
            continue
        amount, days = result
        description = f"{charge.charge_type.name} - {period_label(period_start)}"
        if charge.frequency == LeaseCharge.FREQUENCY_MONTHLY and days is not None and days < days_in_period:
            description += " (part month)"
        kind = charge.charge_type.kind
        specs.append(
            LineSpec(
                kind=kind,
                description=description,
                amount=amount,
                charge_type=charge.charge_type,
            )
        )

    readings = (
        MeterReading.objects.filter(
            unit=lease.unit,
            invoice_line__isnull=True,
            reading_date__gte=lease.start_date,
            reading_date__lte=min(period_end, lease.end_date),
        )
        .select_related("utility_type")
        .order_by("reading_date", "id")
    )
    for reading in readings:
        amount = money(Decimal(reading.consumption) * Decimal(reading.utility_type.rate_per_unit))
        specs.append(
            LineSpec(
                kind=InvoiceLine.KIND_UTILITY,
                description=(
                    f"{reading.utility_type.name} ({reading.reading_date:%d %b}): "
                    f"{reading.previous_value} -> {reading.reading_value} "
                    f"{reading.utility_type.measure}"
                ),
                amount=amount,
                quantity=Decimal(reading.consumption),
                unit_price=Decimal(reading.utility_type.rate_per_unit),
                reading=reading,
            )
        )

    for spec in specs:
        spec.vat_amount = _line_vat(
            spec.kind,
            spec.charge_type,
            spec.amount,
            vat_enabled,
            tenant_vat,
            vat_rate,
        )
    return specs


def totals_for(specs):
    subtotal = money(sum((spec.amount for spec in specs), Decimal("0.00")))
    vat = money(sum((spec.vat_amount for spec in specs), Decimal("0.00")))
    return subtotal, vat, money(subtotal + vat)


def eligible_leases(period_start, period_end):
    return (
        Lease.objects.filter(
            status__in=[Lease.STATUS_ACTIVE, Lease.STATUS_EXPIRED],
            start_date__lte=period_end,
            end_date__gte=period_start,
        )
        .select_related("tenant", "unit", "unit__building")
        .order_by("unit__code", "id")
    )


def preview_lease(lease: Lease, period_start, period_end, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    rent, steps, _next_date = simulate_escalations(lease, period_start)
    specs = build_line_specs(lease, rent, period_start, period_end, settings_obj)
    subtotal, vat, total = totals_for(specs)
    rent_amount = specs[0].amount if specs else Decimal("0.00")
    return {
        "lease": lease,
        "specs": specs,
        "rent_amount": rent_amount,
        "other_amount": money(subtotal - rent_amount),
        "subtotal": subtotal,
        "vat_amount": vat,
        "total": total,
        "escalations": steps,
        "rent_after": rent,
    }


def preview_period(period_start, period_end, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    existing = set(
        Invoice.objects.filter(period_start=period_start).values_list("lease_id", flat=True)
    )
    rows = []
    skipped = 0
    for lease in eligible_leases(period_start, period_end):
        if lease.pk in existing:
            skipped += 1
            continue
        rows.append(preview_lease(lease, period_start, period_end, settings_obj))
    return rows, skipped


def generate_invoice(
    lease: Lease,
    period_start,
    period_end,
    due_date,
    user=None,
    settings_obj=None,
):
    """Create one invoice for a lease and period. Returns (invoice, created)."""
    if Invoice.objects.filter(lease=lease, period_start=period_start).exists():
        return None, False

    try:
        with transaction.atomic():
            if Invoice.objects.filter(lease=lease, period_start=period_start).exists():
                return None, False

            settings_obj = settings_obj or Settings.load()
            user = user or get_current_user()
            rent, steps, next_date = simulate_escalations(lease, period_start)

            if steps:
                for effective_date, old_rent, new_rent in steps:
                    LeaseRentHistory.objects.create(
                        lease=lease,
                        effective_date=effective_date,
                        old_rent=old_rent,
                        new_rent=new_rent,
                        reason=LeaseRentHistory.REASON_ESCALATION,
                        changed_by=user,
                    )
                lease.monthly_rent = rent
                lease.next_escalation_date = next_date
                lease.save(
                    update_fields=[
                        "monthly_rent",
                        "next_escalation_date",
                        "updated_at",
                    ]
                )

            specs = build_line_specs(lease, rent, period_start, period_end, settings_obj)
            subtotal, vat, total = totals_for(specs)
            number = next_document_number(
                NumberSequence.DOC_INVOICE, lease.unit, settings_obj
            )

            invoice = Invoice.objects.create(
                invoice_number=number,
                tenant=lease.tenant,
                lease=lease,
                unit=lease.unit,
                period_start=period_start,
                period_end=period_end,
                issue_date=timezone.localdate(),
                due_date=due_date,
                subtotal=subtotal,
                vat_amount=vat,
                total=total,
                vat_enabled_snapshot=settings_obj.vat_enabled,
                vat_rate_snapshot=Decimal(settings_obj.vat_rate),
                status=Invoice.STATUS_ISSUED,
            )

            for spec in specs:
                line = InvoiceLine.objects.create(
                    invoice=invoice,
                    kind=spec.kind,
                    charge_type=spec.charge_type,
                    description=spec.description,
                    quantity=spec.quantity,
                    unit_price=spec.unit_price,
                    amount=spec.amount,
                    vat_amount=spec.vat_amount,
                )
                if spec.reading is not None:
                    spec.reading.invoice_line = line
                    spec.reading.save(update_fields=["invoice_line", "updated_at"])

            from payments.services import apply_credit_to_invoice

            apply_credit_to_invoice(invoice)

            return invoice, True
    except IntegrityError:
        existing = Invoice.objects.filter(lease=lease, period_start=period_start).first()
        if existing is not None:
            return existing, False
        raise


def generate_period(
    period_start,
    period_end,
    due_date,
    user=None,
    lease_ids=None,
    settings_obj=None,
):
    settings_obj = settings_obj or Settings.load()
    created = []
    skipped = 0
    leases = eligible_leases(period_start, period_end)
    if lease_ids is not None:
        lease_ids = {int(pk) for pk in lease_ids}
        leases = leases.filter(pk__in=lease_ids)

    for lease in leases:
        invoice, made = generate_invoice(
            lease, period_start, period_end, due_date, user=user, settings_obj=settings_obj
        )
        if made:
            created.append(invoice)
        else:
            skipped += 1
    return created, skipped
