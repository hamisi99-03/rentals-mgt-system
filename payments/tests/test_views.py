from decimal import Decimal

import pytest
from django.urls import reverse

from payments.models import Payment
from payments.services import record_payment

pytestmark = pytest.mark.django_db


def test_payment_pages_require_login(client):
    for name in ("payments", "payment_new", "statement_imports"):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


def test_record_payment_page_prefills_invoice(logged_in, invoice):
    response = logged_in.get(
        reverse("payment_new") + f"?tenant={invoice.tenant.pk}&invoice={invoice.pk}"
    )
    assert response.status_code == 200
    assert invoice.invoice_number.encode() in response.content
    assert b"1,000.00" in response.content


def test_allocation_preview_endpoint(logged_in, invoice):
    response = logged_in.get(
        reverse("allocation_preview")
        + f"?tenant={invoice.tenant.pk}&amount=600&withholding_amount=0"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["settlement"] == "600.00"
    assert data["credit"] == "0.00"
    assert data["allocations"][0]["invoice_id"] == invoice.pk
    assert data["allocations"][0]["amount"] == "600.00"


def test_payment_method_is_bank_only(logged_in, invoice):
    from payments.forms import PaymentForm

    choices = dict(PaymentForm().fields["method"].choices)
    assert list(choices) == [Payment.METHOD_BANK]

    response = logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "cash",
            "amount": "1000.00",
        },
    )
    assert response.status_code == 200
    assert Payment.objects.count() == 0


def test_record_payment_auto_allocates(logged_in, invoice):
    response = logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "1000.00",
            "reference": "QK81ABC",
            "notes": "",
        },
    )
    assert response.status_code == 302
    payment = Payment.objects.get()
    assert payment.receipt_number == "RCT-A01-0001"
    assert invoice.balance == Decimal("0.00")

    response = logged_in.get(reverse("payment_detail", kwargs={"pk": payment.pk}))
    assert response.status_code == 200
    assert payment.receipt_number.encode() in response.content

    response = logged_in.get(reverse("payment_pdf", kwargs={"pk": payment.pk}))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    response = logged_in.get(reverse("payment_thermal", kwargs={"pk": payment.pk}))
    assert response.status_code == 200
    assert response.content.startswith(b"\x1b@")
    assert b"RECEIPT" in response.content


def test_record_payment_manual_allocation(logged_in, invoice):
    response = logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "600.00",
            f"allocation_{invoice.pk}": "600.00",
            "notes": "",
        },
    )
    assert response.status_code == 302
    payment = Payment.objects.get()
    allocation = payment.allocations.get()
    assert allocation.amount == Decimal("600.00")
    assert allocation.is_auto is False
    assert invoice.balance == Decimal("400.00")


def test_payments_list_and_filters(logged_in, invoice):
    logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "1000.00",
        },
    )
    payment = Payment.objects.get()
    response = logged_in.get(reverse("payments"))
    assert response.status_code == 200
    assert payment.receipt_number.encode() in response.content

    response = logged_in.get(reverse("payments") + "?q=nothing")
    assert payment.receipt_number.encode() not in response.content


def test_void_payment_view(logged_in, invoice):
    logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "1000.00",
        },
    )
    payment = Payment.objects.get()
    response = logged_in.post(
        reverse("payment_void", kwargs={"pk": payment.pk}),
        {"reason": "Wrong amount"},
    )
    assert response.status_code == 302
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_VOID
    assert invoice.balance == Decimal("1000.00")


def test_cheque_actions_view(logged_in, invoice):
    payment = record_payment(
        invoice.tenant,
        invoice.issue_date,
        Payment.METHOD_CHEQUE,
        Decimal("1000.00"),
        cheque_number="12345",
        cheque_bank="Equity",
    )
    logged_in.post(reverse("cheque_banked", kwargs={"pk": payment.pk}))
    payment.refresh_from_db()
    assert payment.cheque_status == Payment.CHEQUE_BANKED

    logged_in.post(reverse("cheque_bounced", kwargs={"pk": payment.pk}))
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_VOID
    assert payment.cheque_status == Payment.CHEQUE_BOUNCED
    assert invoice.balance == Decimal("1000.00")


def test_tenant_statement_and_payments_tabs(logged_in, invoice):
    logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "1000.00",
        },
    )
    payment = Payment.objects.get()
    response = logged_in.get(
        reverse("tenant_detail", kwargs={"pk": invoice.tenant.pk}) + "?tab=statement"
    )
    assert response.status_code == 200
    assert payment.receipt_number.encode() in response.content

    response = logged_in.get(
        reverse("tenant_detail", kwargs={"pk": invoice.tenant.pk}) + "?tab=payments"
    )
    assert response.status_code == 200
    assert payment.receipt_number.encode() in response.content


def test_invoice_detail_shows_payment(logged_in, invoice):
    logged_in.post(
        reverse("payment_new"),
        {
            "tenant": invoice.tenant.pk,
            "date_received": invoice.issue_date.isoformat(),
            "method": "bank",
            "amount": "400.00",
        },
    )
    response = logged_in.get(reverse("invoice_detail", kwargs={"pk": invoice.pk}))
    assert response.status_code == 200
    assert invoice.balance == Decimal("600.00")
    assert b"600.00" in response.content


def test_statement_pages_require_login_and_render(logged_in, invoice):
    response = logged_in.get(reverse("statement_imports"))
    assert response.status_code == 200
