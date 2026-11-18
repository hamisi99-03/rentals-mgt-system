from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from payments.services import record_payment
from property.models import TenantContact
from reports.services import dashboard_summary

pytestmark = pytest.mark.django_db


def test_report_pages_require_login(client):
    for name in (
        "reports",
        "report_arrears",
        "report_monthly",
        "report_occupancy",
        "report_statement",
        "report_tax",
        "overdue_reminders",
    ):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


def test_dashboard_renders_ledger_numbers(logged_in, invoice, overdue_invoice):
    payment = record_payment(
        invoice.tenant, timezone.localdate(), "cash", Decimal("300.00")
    )
    response = logged_in.get(reverse("dashboard"))
    assert response.status_code == 200
    assert b"income-expense-data" in response.content
    assert b"arrears-data" in response.content
    summary = response.context["summary"]
    assert summary["rent_due"] == invoice.total
    assert summary["collected"] == payment.settlement_amount
    assert summary["arrears"] == overdue_invoice.balance
    assert summary["occupied_label"] == "1 / 1"


def test_report_pages_render(logged_in, invoice, expense):
    today = timezone.localdate().isoformat()
    urls = [
        reverse("reports"),
        reverse("report_arrears") + f"?as_of={today}",
        reverse("report_monthly"),
        reverse("report_occupancy"),
        reverse("report_statement"),
        reverse("report_statement") + f"?tenant={invoice.tenant.pk}",
        reverse("report_tax"),
        reverse("overdue_reminders"),
    ]
    for url in urls:
        response = logged_in.get(url)
        assert response.status_code == 200, url


def test_arrears_exports(logged_in, overdue_invoice):
    today = timezone.localdate().isoformat()
    response = logged_in.get(
        reverse("report_arrears") + f"?as_of={today}&export=xlsx"
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(response.content))
    assert "Report" in workbook.sheetnames

    response = logged_in.get(
        reverse("report_arrears") + f"?as_of={today}&export=pdf"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_monthly_tax_and_occupancy_exports(logged_in, invoice, expense):
    today = timezone.localdate()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    for name, query in (
        ("report_monthly", f"?start_date={start}&end_date={end}"),
        ("report_tax", f"?start_date={start}&end_date={end}"),
        ("report_occupancy", ""),
        ("overdue_reminders", ""),
    ):
        path = reverse(name) + query
        separator = "&" if query else "?"
        response = logged_in.get(path + separator + "export=xlsx")
        assert response.status_code == 200, name
        workbook = load_workbook(BytesIO(response.content))
        assert "Report" in workbook.sheetnames

        response = logged_in.get(path + separator + "export=pdf")
        assert response.status_code == 200, name
        assert response.content.startswith(b"%PDF")


def test_statement_exports(logged_in, invoice):
    payment = record_payment(
        invoice.tenant, timezone.localdate(), "cash", Decimal("400.00")
    )
    today = timezone.localdate()
    start = (today - timedelta(days=180)).isoformat()
    end = today.isoformat()
    path = (
        reverse("report_statement")
        + f"?tenant={invoice.tenant.pk}&start_date={start}&end_date={end}"
    )
    response = logged_in.get(path + "&export=xlsx")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert "Report" in workbook.sheetnames

    response = logged_in.get(path + "&export=pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert payment.settlement_amount == Decimal("400.00")


def test_reminder_buttons_render(logged_in, overdue_invoice, tenant):
    TenantContact.objects.create(
        tenant=tenant, name="Asha", phone="+254700000001", is_primary=True
    )
    response = logged_in.get(reverse("overdue_reminders"))
    assert response.status_code == 200
    assert b"https://wa.me/254700000001" in response.content
    assert b"tel:+254700000001" in response.content


def test_dashboard_summary_function_matches_view(logged_in, invoice, overdue_invoice, expense):
    response = logged_in.get(reverse("dashboard"))
    summary = response.context["summary"]
    expected = dashboard_summary()
    assert summary["rent_due"] == expected["rent_due"]
    assert summary["collected"] == expected["collected"]
    assert summary["arrears"] == expected["arrears"]
    assert summary["occupied"] == expected["occupied"]
