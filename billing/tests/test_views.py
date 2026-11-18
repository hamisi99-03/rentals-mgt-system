from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from billing.models import (
    ChargeType,
    Invoice,
    LeaseCharge,
    MeterReading,
    UtilityType,
)
from property.models import Lease, Tenant, Unit

pytestmark = pytest.mark.django_db


def test_billing_pages_require_login(client):
    for name in ("billing", "invoices", "charge_types", "utility_types", "meter_readings"):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


def test_billing_preview_shows_lease(logged_in, lease):
    response = logged_in.get(reverse("billing") + "?period=2026-01&due_date=2026-01-05")
    assert response.status_code == 200
    assert lease.unit.code.encode() in response.content
    assert lease.tenant.business_name.encode() in response.content
    assert b"Generate 1 invoice" in response.content
    assert Invoice.objects.count() == 0


def test_generate_selected_lease(logged_in, lease):
    response = logged_in.post(
        reverse("billing_generate"),
        {
            "period": "2026-01",
            "due_date": "2026-01-05",
            "lease_ids": [lease.pk],
        },
    )
    assert response.status_code == 302
    invoice = Invoice.objects.get(lease=lease)
    assert invoice.invoice_number == "INV-A01-0001"
    assert invoice.total == Decimal("1000.00")

    response = logged_in.get(reverse("invoice_detail", kwargs={"pk": invoice.pk}))
    assert response.status_code == 200
    assert invoice.invoice_number.encode() in response.content


def test_generate_without_selection_warns(logged_in, lease):
    response = logged_in.post(
        reverse("billing_generate"),
        {"period": "2026-01", "due_date": "2026-01-05"},
    )
    assert response.status_code == 302
    assert Invoice.objects.count() == 0


def test_billing_run_invalid_period(logged_in):
    response = logged_in.get(reverse("billing") + "?period=bad")
    assert response.status_code == 200
    assert b"valid period" in response.content


def test_invoice_list_and_filters(logged_in, lease):
    start, end = (date(2026, 1, 1), date(2026, 1, 31))
    from billing.services import generate_invoice

    invoice, _ = generate_invoice(lease, start, end, date(2026, 1, 5))

    response = logged_in.get(reverse("invoices"))
    assert response.status_code == 200
    assert invoice.invoice_number.encode() in response.content

    response = logged_in.get(reverse("invoices") + "?q=Unknown")
    assert invoice.invoice_number.encode() not in response.content

    response = logged_in.get(reverse("invoices") + "?period=2026-01")
    assert invoice.invoice_number.encode() in response.content


def test_invoice_pdf_and_period_pdf(logged_in, lease):
    start, end = (date(2026, 1, 1), date(2026, 1, 31))
    from billing.services import generate_invoice

    invoice, _ = generate_invoice(lease, start, end, date(2026, 1, 5))

    response = logged_in.get(reverse("invoice_pdf", kwargs={"pk": invoice.pk}))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert invoice.invoice_number.encode() in response["Content-Disposition"].encode()

    response = logged_in.get(reverse("invoice_period_pdf") + "?period=2026-01")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_period_pdf_without_invoices_redirects(logged_in):
    response = logged_in.get(reverse("invoice_period_pdf") + "?period=2026-01")
    assert response.status_code == 302


def test_charge_types_create_edit_and_toggle(logged_in):
    response = logged_in.post(
        reverse("charge_types"),
        {
            "name": "Security",
            "kind": "service",
            "vat_applicable": "on",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    charge_type = ChargeType.objects.get(name="Security")
    assert charge_type.vat_applicable is True

    response = logged_in.post(
        reverse("charge_type_edit", kwargs={"pk": charge_type.pk}),
        {
            "name": "Security fee",
            "kind": "service",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    charge_type.refresh_from_db()
    assert charge_type.name == "Security fee"

    logged_in.post(reverse("charge_type_toggle", kwargs={"pk": charge_type.pk}))
    charge_type.refresh_from_db()
    assert charge_type.is_active is False


def test_lease_charges_create_and_toggle(logged_in, lease, service_type):
    response = logged_in.get(reverse("lease_charges", kwargs={"lease_pk": lease.pk}))
    assert response.status_code == 200

    response = logged_in.post(
        reverse("lease_charges", kwargs={"lease_pk": lease.pk}),
        {
            "charge_type": service_type.pk,
            "amount": "300.00",
            "frequency": "monthly",
            "start_date": "2026-01-01",
            "end_date": "",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    charge = LeaseCharge.objects.get(lease=lease, charge_type=service_type)
    assert charge.amount == Decimal("300.00")

    logged_in.post(reverse("lease_charge_toggle", kwargs={"pk": charge.pk}))
    charge.refresh_from_db()
    assert charge.is_active is False


def test_utility_types_create_and_toggle(logged_in):
    response = logged_in.post(
        reverse("utility_types"),
        {
            "name": "Electricity",
            "measure": "kWh",
            "rate_per_unit": "25.00",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    utility = UtilityType.objects.get(name="Electricity")
    assert utility.rate_per_unit == Decimal("25.00")

    logged_in.post(reverse("utility_type_toggle", kwargs={"pk": utility.pk}))
    utility.refresh_from_db()
    assert utility.is_active is False


def test_meter_reading_create_calculates_previous(logged_in, unit, utility_type):
    response = logged_in.get(reverse("meter_readings"))
    assert response.status_code == 200

    response = logged_in.post(
        reverse("meter_readings"),
        {
            "unit": unit.pk,
            "utility_type": utility_type.pk,
            "reading_date": "2026-01-05",
            "reading_value": "100.00",
        },
    )
    assert response.status_code == 302
    first = MeterReading.objects.get(reading_date=date(2026, 1, 5))
    assert first.previous_value == Decimal("0.00")
    assert first.consumption == Decimal("100.00")

    logged_in.post(
        reverse("meter_readings"),
        {
            "unit": unit.pk,
            "utility_type": utility_type.pk,
            "reading_date": "2026-01-25",
            "reading_value": "150.00",
        },
    )
    second = MeterReading.objects.get(reading_date=date(2026, 1, 25))
    assert second.previous_value == Decimal("100.00")
    assert second.consumption == Decimal("50.00")


def test_meter_reading_lower_than_previous_is_rejected(logged_in, unit, utility_type):
    MeterReading.objects.create(
        unit=unit,
        utility_type=utility_type,
        reading_date=date(2026, 1, 5),
        reading_value=Decimal("100.00"),
    )
    response = logged_in.post(
        reverse("meter_readings"),
        {
            "unit": unit.pk,
            "utility_type": utility_type.pk,
            "reading_date": "2026-01-25",
            "reading_value": "50.00",
        },
    )
    assert response.status_code == 200
    assert MeterReading.objects.count() == 1


def test_billed_meter_reading_is_locked(logged_in, lease, unit, utility_type):
    reading = MeterReading.objects.create(
        unit=unit,
        utility_type=utility_type,
        reading_date=date(2026, 1, 5),
        reading_value=Decimal("100.00"),
    )
    from billing.services import generate_invoice

    generate_invoice(lease, date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 5))
    reading.refresh_from_db()
    assert reading.invoice_line_id is not None

    response = logged_in.get(reverse("meter_reading_edit", kwargs={"pk": reading.pk}))
    assert response.status_code == 302
    logged_in.post(reverse("meter_reading_delete", kwargs={"pk": reading.pk}))
    assert MeterReading.objects.filter(pk=reading.pk).exists()


def test_meter_readings_filters(logged_in, unit, utility_type):
    MeterReading.objects.create(
        unit=unit,
        utility_type=utility_type,
        reading_date=date(2026, 1, 5),
        reading_value=Decimal("100.00"),
    )
    response = logged_in.get(reverse("meter_readings") + f"?unit={unit.pk}&billed=no")
    assert response.status_code == 200
    assert b"100" in response.content

def test_management_pages_render(logged_in, lease, service_type, utility_type, unit):
    assert logged_in.get(reverse("charge_types")).status_code == 200
    assert logged_in.get(reverse("utility_types")).status_code == 200
    assert logged_in.get(reverse("lease_charges", kwargs={"lease_pk": lease.pk})).status_code == 200

    reading = MeterReading.objects.create(
        unit=unit,
        utility_type=utility_type,
        reading_date=date(2026, 1, 5),
        reading_value=Decimal("100.00"),
    )
    assert logged_in.get(reverse("meter_reading_edit", kwargs={"pk": reading.pk})).status_code == 200

    charge = LeaseCharge.objects.create(
        lease=lease,
        charge_type=service_type,
        amount=Decimal("300.00"),
        frequency=LeaseCharge.FREQUENCY_MONTHLY,
        start_date=date(2026, 1, 1),
    )
    assert logged_in.get(reverse("lease_charge_edit", kwargs={"pk": charge.pk})).status_code == 200
    assert logged_in.get(reverse("charge_type_edit", kwargs={"pk": service_type.pk})).status_code == 200
    assert logged_in.get(reverse("utility_type_edit", kwargs={"pk": utility_type.pk})).status_code == 200

def test_vat_invoice_pdf_builds(logged_in, lease, tenant, settings_obj):
    settings_obj.vat_enabled = True
    settings_obj.save()
    tenant.vat_applicable = True
    tenant.save()

    from billing.pdf import build_invoice_pdf
    from billing.services import generate_invoice

    invoice, _ = generate_invoice(
        lease, date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 5)
    )
    pdf = build_invoice_pdf(invoice)
    assert pdf.getvalue().startswith(b"%PDF")
