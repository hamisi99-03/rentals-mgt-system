from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.services import add_months
from payments.services import record_payment
from property.models import TenantContact
from reports.services import (
    arrears_buckets,
    arrears_report,
    dashboard_summary,
    monthly_income_expense,
    normalize_phone,
    occupancy_report,
    overdue_reminders,
    tax_summary,
    tenant_statement,
)
from billing.models import Invoice

from .conftest import make_invoice

pytestmark = pytest.mark.django_db


def test_dashboard_reconciles_with_the_ledger(invoice, overdue_invoice, expense, unit):
    payment = record_payment(
        invoice.tenant,
        timezone.localdate(),
        "cash",
        Decimal("300.00"),
    )
    summary = dashboard_summary()

    assert summary["rent_due"] == invoice.total
    assert summary["collected"] == payment.settlement_amount
    assert summary["arrears"] == overdue_invoice.balance
    assert sum(summary["buckets"].values()) == summary["arrears"]
    assert summary["occupied"] == 1
    assert summary["total_units"] == 1
    assert summary["overdue_tenants"] == 1
    assert summary["months"][-1]["income"] == float(payment.settlement_amount)
    assert summary["months"][-1]["expenses"] == float(expense.amount)


def test_arrears_buckets(lease):
    today = timezone.localdate()
    due_dates = [
        today - timedelta(days=5),
        today - timedelta(days=40),
        today - timedelta(days=75),
        today - timedelta(days=120),
    ]
    for index, due in enumerate(due_dates):
        invoice = make_invoice(lease, months_ago=index, due=due)
        Invoice.objects.filter(pk=invoice.pk).update(due_date=due)

    buckets = arrears_buckets(today)
    assert buckets["0-30"] == Decimal("1000.00")
    assert buckets["31-60"] == Decimal("1000.00")
    assert buckets["61-90"] == Decimal("1000.00")
    assert buckets["90+"] == Decimal("1000.00")

    rows, summary = arrears_report(today)
    assert len(rows) == 4
    assert sum(summary.values()) == Decimal("4000.00")
    assert {row["bucket"] for row in rows} == {"0-30", "31-60", "61-90", "90+"}


def test_monthly_income_and_expense(invoice, expense):
    today = timezone.localdate()
    start = today.replace(day=1)
    end = add_months(start, 1) - timedelta(days=1)
    payment = record_payment(invoice.tenant, today, "cash", Decimal("400.00"))

    rows = monthly_income_expense(start, end)
    assert len(rows) == 1
    assert rows[0]["billed"] == invoice.total
    assert rows[0]["collected"] == payment.settlement_amount
    assert rows[0]["expenses"] == expense.amount
    assert rows[0]["net"] == payment.settlement_amount - expense.amount


def test_occupancy_report(lease, unit):
    rows, counts, rate = occupancy_report()
    assert rows[0]["status"] == "Occupied"
    assert counts["occupied"] == 1
    assert counts["vacant"] == 0
    assert rate == Decimal("100.00")


def test_tenant_statement(invoice):
    payment = record_payment(
        invoice.tenant, timezone.localdate(), "cash", Decimal("600.00")
    )
    start = invoice.issue_date - timedelta(days=1)
    end = timezone.localdate() + timedelta(days=1)
    statement = tenant_statement(invoice.tenant, start, end)
    assert statement["opening"] == Decimal("0.00")
    assert len(statement["rows"]) == 2
    assert statement["closing"] == invoice.total - payment.settlement_amount

    empty = tenant_statement(invoice.tenant, end + timedelta(days=10), end + timedelta(days=20))
    assert empty["opening"] == invoice.total - payment.settlement_amount
    assert empty["rows"] == []
    assert empty["closing"] == empty["opening"]


def test_tax_summary(settings_obj, tenant, lease):
    settings_obj.vat_enabled = True
    settings_obj.save()
    tenant.vat_applicable = True
    tenant.save()

    invoice = make_invoice(lease)
    record_payment(
        tenant,
        timezone.localdate(),
        "mpesa",
        Decimal("900.00"),
        withholding_amount=Decimal("100.00"),
    )

    start = timezone.localdate().replace(day=1)
    end = add_months(start, 1) - timedelta(days=1)
    rows = tax_summary(start, end)
    assert invoice.vat_amount == Decimal("160.00")
    assert len(rows) == 1
    assert rows[0]["invoices"] == 1
    assert rows[0]["rent_billed"] == Decimal("1000.00")
    assert rows[0]["vat_charged"] == Decimal("160.00")
    assert rows[0]["withholding"] == Decimal("100.00")


def test_overdue_reminder_links(overdue_invoice, tenant):
    TenantContact.objects.create(
        tenant=tenant, name="Asha", phone="+254700000001", is_primary=True
    )
    rows = overdue_reminders()
    assert len(rows) == 1
    row = rows[0]
    assert row["tenant"] == tenant
    assert row["balance"] == overdue_invoice.balance
    assert "https://wa.me/254700000001?text=" in row["whatsapp_url"]
    assert row["call_url"] == "tel:+254700000001"
    assert tenant.business_name in row["message"]
    assert overdue_invoice.invoice_number in row["message"]


def test_normalize_phone():
    assert normalize_phone("0700000001") == "254700000001"
    assert normalize_phone("+254 700 000 001") == "254700000001"
    assert normalize_phone("700000001") == "254700000001"
    assert normalize_phone("") == ""
