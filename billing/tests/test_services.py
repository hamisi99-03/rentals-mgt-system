from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from billing.models import ChargeType, Invoice, InvoiceLine, LeaseCharge
from billing.services import (
    eligible_leases,
    generate_invoice,
    generate_period,
    parse_period,
    preview_period,
)
from property.models import Lease

from .conftest import add_charge, add_reading

pytestmark = pytest.mark.django_db

JAN = ("2026-01", date(2026, 1, 5))
FEB = ("2026-02", date(2026, 2, 5))


def generate(lease, period):
    start, end = parse_period(period[0])
    return generate_invoice(lease, start, end, period[1])


def test_full_month_invoice(lease):
    invoice, created = generate(lease, JAN)
    assert created is True
    assert invoice.subtotal == Decimal("1000.00")
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.total == Decimal("1000.00")
    rent_line = invoice.lines.get(kind=InvoiceLine.KIND_RENT)
    assert rent_line.amount == Decimal("1000.00")
    assert invoice.period_start == date(2026, 1, 1)
    assert invoice.period_end == date(2026, 1, 31)


def test_mid_month_start_prorates_on_thirty_day_month(make_lease):
    lease = make_lease(start_date=date(2026, 1, 16), rent="3000.00")
    invoice, _ = generate(lease, JAN)
    rent_line = invoice.lines.get(kind=InvoiceLine.KIND_RENT)
    assert rent_line.amount == Decimal("1600.00")


def test_mid_month_end_prorates_on_thirty_day_month(make_lease):
    lease = make_lease(start_date=date(2025, 1, 1), end_date=date(2026, 1, 15), rent="3000.00")
    invoice, _ = generate(lease, JAN)
    rent_line = invoice.lines.get(kind=InvoiceLine.KIND_RENT)
    assert rent_line.amount == Decimal("1500.00")


def test_full_february_bills_full_amount_but_partial_uses_thirty_day_month(make_lease):
    full = make_lease(start_date=date(2026, 2, 1), end_date=date(2026, 2, 28), rent="3000.00")
    invoice, _ = generate(full, FEB)
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("3000.00")

    partial = make_lease(start_date=date(2026, 2, 16), end_date=date(2026, 2, 28), rent="3000.00")
    invoice, _ = generate(partial, FEB)
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("1300.00")


def test_monthly_charge_prorates_and_full_charges_bill_in_full(make_lease, service_type):
    lease = make_lease(start_date=date(2026, 1, 1), rent="1000.00")
    add_charge(lease, service_type, amount="300.00", start=date(2026, 1, 16))
    invoice, _ = generate(lease, JAN)
    charge_line = invoice.lines.get(kind=InvoiceLine.KIND_SERVICE)
    assert charge_line.amount == Decimal("160.00")

    quarterly_type = ChargeType.objects.create(name="Quarterly fee", kind=ChargeType.KIND_SERVICE)
    add_charge(
        lease,
        quarterly_type,
        amount="900.00",
        frequency=LeaseCharge.FREQUENCY_QUARTERLY,
        start=date(2026, 1, 16),
    )
    invoice, _ = generate(lease, FEB)
    assert not invoice.lines.filter(charge_type=quarterly_type).exists()
    invoice, _ = generate(lease, ("2026-04", date(2026, 4, 5)))
    assert invoice.lines.get(charge_type=quarterly_type).amount == Decimal("900.00")


def test_once_charge_bills_only_in_start_month(make_lease, service_type):
    lease = make_lease(start_date=date(2026, 1, 1), rent="1000.00")
    add_charge(
        lease,
        service_type,
        amount="500.00",
        frequency=LeaseCharge.FREQUENCY_ONCE,
        start=date(2026, 1, 16),
    )
    jan, _ = generate(lease, JAN)
    feb, _ = generate(lease, FEB)
    assert jan.lines.filter(charge_type=service_type).count() == 1
    assert not feb.lines.filter(charge_type=service_type).exists()


def test_percentage_escalation_applies_and_records_history(make_lease, settings_obj):
    lease = make_lease(
        start_date=date(2025, 6, 1),
        end_date=date(2027, 12, 31),
        rent="1000.00",
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("10.00"),
        escalation_interval_months=12,
        next_escalation_date=date(2026, 1, 1),
    )
    invoice, _ = generate(lease, JAN)
    lease.refresh_from_db()
    assert lease.monthly_rent == Decimal("1100.00")
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("1100.00")
    assert lease.next_escalation_date == date(2027, 1, 1)
    history = lease.rent_history.get(reason="escalation")
    assert history.old_rent == Decimal("1000.00")
    assert history.new_rent == Decimal("1100.00")


def test_escalation_not_applied_before_due_date(make_lease):
    lease = make_lease(
        start_date=date(2025, 6, 1),
        end_date=date(2027, 12, 31),
        rent="1000.00",
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("10.00"),
        escalation_interval_months=12,
        next_escalation_date=date(2026, 1, 1),
    )
    invoice, _ = generate(lease, ("2025-12", date(2025, 12, 5)))
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("1000.00")
    assert not lease.rent_history.exists()


def test_missed_escalations_compound(make_lease):
    lease = make_lease(
        start_date=date(2024, 6, 1),
        end_date=date(2027, 12, 31),
        rent="1000.00",
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("10.00"),
        escalation_interval_months=6,
        next_escalation_date=date(2025, 1, 1),
    )
    invoice, _ = generate(lease, JAN)
    lease.refresh_from_db()
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("1331.00")
    assert lease.monthly_rent == Decimal("1331.00")
    assert lease.next_escalation_date == date(2026, 7, 1)
    assert lease.rent_history.filter(reason="escalation").count() == 3


def test_fixed_escalation(make_lease):
    lease = make_lease(
        start_date=date(2025, 6, 1),
        end_date=date(2027, 12, 31),
        rent="1000.00",
        escalation_type=Lease.ESCALATION_FIXED,
        escalation_value=Decimal("100.00"),
        escalation_interval_months=12,
        next_escalation_date=date(2026, 1, 1),
    )
    invoice, _ = generate(lease, JAN)
    assert invoice.lines.get(kind=InvoiceLine.KIND_RENT).amount == Decimal("1100.00")


def test_vat_off_master_switch(lease, tenant, settings_obj):
    settings_obj.vat_enabled = False
    settings_obj.save()
    tenant.vat_applicable = True
    tenant.save()

    invoice, _ = generate(lease, JAN)
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.total == Decimal("1000.00")
    assert all(line.vat_amount == 0 for line in invoice.lines.all())


def test_vat_requires_tenant_flag(lease, tenant, settings_obj):
    settings_obj.vat_enabled = True
    settings_obj.save()
    tenant.vat_applicable = False
    tenant.save()

    invoice, _ = generate(lease, JAN)
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.total == Decimal("1000.00")


def test_vat_scope_rent_utilities_and_charge_types(lease, tenant, service_type, settings_obj):
    settings_obj.vat_enabled = True
    settings_obj.vat_rate = Decimal("16.00")
    settings_obj.save()
    tenant.vat_applicable = True
    tenant.save()

    vatable_service = service_type
    vatable_service.vat_applicable = True
    vatable_service.save()
    non_vatable = ChargeType.objects.create(
        name="Cleaning", kind=ChargeType.KIND_SERVICE, vat_applicable=False
    )
    add_charge(lease, vatable_service, amount="500.00")
    add_charge(lease, non_vatable, amount="300.00")

    invoice, _ = generate(lease, JAN)
    rent_line = invoice.lines.get(kind=InvoiceLine.KIND_RENT)
    vatable_line = invoice.lines.get(charge_type=vatable_service)
    non_vatable_line = invoice.lines.get(charge_type=non_vatable)

    assert rent_line.vat_amount == Decimal("160.00")
    assert vatable_line.vat_amount == Decimal("80.00")
    assert non_vatable_line.vat_amount == Decimal("0.00")
    assert invoice.vat_amount == Decimal("240.00")
    assert invoice.total == Decimal("2040.00")


def test_vat_is_snapshotted(lease, tenant, settings_obj):
    settings_obj.vat_enabled = True
    settings_obj.vat_rate = Decimal("16.00")
    settings_obj.save()
    tenant.vat_applicable = True
    tenant.save()

    first, _ = generate(lease, JAN)
    assert first.vat_rate_snapshot == Decimal("16.00")
    assert first.vat_amount == Decimal("160.00")

    settings_obj.vat_rate = Decimal("20.00")
    settings_obj.vat_enabled = False
    settings_obj.save()

    first.refresh_from_db()
    assert first.vat_amount == Decimal("160.00")
    assert first.total == Decimal("1160.00")

    second, _ = generate(lease, FEB)
    assert second.vat_enabled_snapshot is False
    assert second.vat_amount == Decimal("0.00")


def test_generation_is_idempotent(lease):
    first, created = generate(lease, JAN)
    second, created_again = generate(lease, JAN)
    assert created is True
    assert created_again is False
    assert second is None
    assert Invoice.objects.count() == 1
    assert first.invoice_number == "INV-A01-0001"


def test_generate_period_skips_existing(lease):
    start, end = parse_period("2026-01")
    created, skipped = generate_period(start, end, JAN[1])
    assert len(created) == 1
    assert skipped == 0

    created, skipped = generate_period(start, end, JAN[1])
    assert created == []
    assert skipped == 1


def test_management_command_is_idempotent(lease):
    out = StringIO()
    call_command("generate_invoices", period="2026-01", stdout=out)
    assert Invoice.objects.count() == 1

    out = StringIO()
    call_command("generate_invoices", period="2026-01", stdout=out)
    assert Invoice.objects.count() == 1
    assert "skipped 1" in out.getvalue()


def test_utility_lines_bill_consumption_and_link_readings(
    lease, unit, utility_type, settings_obj
):
    first = add_reading(unit, utility_type, date(2026, 1, 5), "100")
    second = add_reading(unit, utility_type, date(2026, 1, 25), "150")
    assert second.previous_value == Decimal("100.00")
    assert second.consumption == Decimal("50.00")

    invoice, _ = generate(lease, JAN)
    utility_lines = invoice.lines.filter(kind=InvoiceLine.KIND_UTILITY).order_by("id")
    assert utility_lines.count() == 2
    assert utility_lines[0].amount == Decimal("5000.00")
    assert utility_lines[1].amount == Decimal("2500.00")
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.invoice_line_id is not None
    assert second.invoice_line_id is not None

    next_period = add_reading(unit, utility_type, date(2026, 2, 5), "180")
    feb, _ = generate(lease, FEB)
    assert feb.lines.filter(kind=InvoiceLine.KIND_UTILITY).count() == 1
    assert feb.lines.get(kind=InvoiceLine.KIND_UTILITY).amount == Decimal("1500.00")
    next_period.refresh_from_db()
    assert next_period.invoice_line_id is not None


def test_preview_does_not_consume_readings(lease, unit, utility_type):
    reading = add_reading(unit, utility_type, date(2026, 1, 5), "100")
    start, end = parse_period("2026-01")
    preview_period(start, end)
    preview_period(start, end)
    reading.refresh_from_db()
    assert reading.invoice_line_id is None


def test_eligibility_includes_expired_and_excludes_draft_terminated(make_lease, make_unit):
    expired = make_lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 20),
        rent="3000.00",
        status=Lease.STATUS_EXPIRED,
    )
    draft = make_lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        status=Lease.STATUS_DRAFT,
    )
    terminated = make_lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        status=Lease.STATUS_TERMINATED,
    )
    outside = make_lease(
        start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
    )

    start, end = parse_period("2026-01")
    eligible = set(eligible_leases(start, end))
    assert expired in eligible
    assert draft not in eligible
    assert terminated not in eligible
    assert outside not in eligible

    rows, skipped = preview_period(start, end)
    by_lease = {row["lease"].pk: row for row in rows}
    assert expired.pk in by_lease
    assert by_lease[expired.pk]["rent_amount"] == Decimal("2000.00")
    assert skipped == 0


def test_preview_reports_escalation(make_lease):
    lease = make_lease(
        start_date=date(2025, 6, 1),
        end_date=date(2027, 12, 31),
        rent="1000.00",
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("10.00"),
        escalation_interval_months=12,
        next_escalation_date=date(2026, 1, 1),
    )
    start, end = parse_period("2026-01")
    rows, _ = preview_period(start, end)
    row = next(row for row in rows if row["lease"].pk == lease.pk)
    assert row["escalations"]
    assert row["rent_after"] == Decimal("1100.00")
    assert row["total"] == Decimal("1100.00")
