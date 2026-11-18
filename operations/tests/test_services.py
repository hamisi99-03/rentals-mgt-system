from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from billing.models import MeterReading, UtilityType
from operations.models import Deposit, MoveOut, MoveOutItem
from operations.pdf import build_move_out_pdf
from operations.services import (
    compute_move_out,
    create_move_out,
    held_deposit_total,
    record_deposit,
    record_final_readings,
    settle_move_out,
)
from property.models import Unit

pytestmark = pytest.mark.django_db


def test_deposit_receipt_and_total(lease):
    deposit = record_deposit(lease, "2000.00", timezone.localdate())
    assert deposit.status == Deposit.STATUS_HELD
    assert held_deposit_total(lease) == Decimal("2000.00")


def test_deposit_must_be_positive(lease):
    with pytest.raises(ValidationError):
        record_deposit(lease, "0", timezone.localdate())


def test_move_out_computes_refund(lease, invoice):
    record_deposit(lease, "2000.00", timezone.localdate())
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=30))
    shutter = move_out.items.get(item=MoveOutItem.ITEM_SHUTTER)
    shutter.condition = "damaged"
    shutter.damage_cost = Decimal("300.00")
    shutter.save()

    compute_move_out(move_out)
    assert move_out.arrears_at_exit == Decimal("1000.00")
    assert move_out.deposit_held == Decimal("2000.00")
    assert move_out.damages_amount == Decimal("300.00")
    assert move_out.refund_amount == Decimal("700.00")
    assert move_out.remaining_balance == Decimal("0.00")


def test_move_out_negative_refund_is_floored(lease, invoice):
    record_deposit(lease, "500.00", timezone.localdate())
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=30))
    shutter = move_out.items.get(item=MoveOutItem.ITEM_SHUTTER)
    shutter.damage_cost = Decimal("200.00")
    shutter.save()
    compute_move_out(move_out)
    assert move_out.refund_amount == Decimal("0.00")
    assert move_out.remaining_balance == Decimal("700.00")


def test_duplicate_planned_move_out_is_blocked(lease):
    create_move_out(lease, timezone.localdate() + timedelta(days=30))
    with pytest.raises(ValidationError):
        create_move_out(lease, timezone.localdate() + timedelta(days=31))


def test_settle_move_out_refunds_deposit_and_terminates_lease(lease, invoice, unit):
    record_deposit(lease, "2000.00", timezone.localdate())
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=30))
    compute_move_out(move_out)
    settle_move_out(move_out)

    move_out.refresh_from_db()
    lease.refresh_from_db()
    unit.refresh_from_db()
    assert move_out.status == MoveOut.STATUS_SETTLED
    assert lease.status == "terminated"
    assert unit.status == Unit.STATUS_VACANT
    deposit = lease.deposits.get()
    assert deposit.status == Deposit.STATUS_PARTLY_REFUNDED

    refund = move_out.refund_amount
    held = move_out.deposit_held
    compute_move_out(move_out)
    move_out.refresh_from_db()
    assert move_out.refund_amount == refund
    assert move_out.deposit_held == held


def test_settle_with_no_deposit(lease):
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=30))
    compute_move_out(move_out)
    settle_move_out(move_out)
    move_out.refresh_from_db()
    assert move_out.refund_amount == Decimal("0.00")
    lease.refresh_from_db()
    assert lease.status == "terminated"


def test_move_out_pdf_builds(lease):
    record_deposit(lease, "2000.00", timezone.localdate())
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=30))
    pdf = build_move_out_pdf(move_out)
    assert pdf.getvalue().startswith(b"%PDF")


def test_final_readings_create_meter_reading(lease, unit):
    utility = UtilityType.objects.create(name="Water", measure="m3", rate_per_unit=50)
    move_out_date = timezone.localdate() + timedelta(days=5)
    record_final_readings(lease, move_out_date, [(utility, "100.00")])
    reading = MeterReading.objects.get(
        unit=unit, utility_type=utility, reading_date=move_out_date
    )
    assert reading.reading_value == Decimal("100.00")


def test_final_readings_reject_lower_value(lease, unit):
    utility = UtilityType.objects.create(name="Water", measure="m3", rate_per_unit=50)
    MeterReading.objects.create(
        unit=unit,
        utility_type=utility,
        reading_date=timezone.localdate(),
        reading_value=Decimal("100.00"),
    )
    move_out_date = timezone.localdate() + timedelta(days=5)
    with pytest.raises(ValidationError):
        record_final_readings(lease, move_out_date, [(utility, "90.00")])
