from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from billing.models import Invoice
from core.models import AuditLog
from payments.models import (
    CreditEntry,
    Payment,
    PaymentAllocation,
    StatementImport,
    StatementRow,
)
from payments.services import (
    credit_balance,
    mark_cheque_banked,
    mark_cheque_bounced,
    record_payment,
    void_payment,
)
from property.models import Tenant, Unit
from billing.services import add_months, generate_invoice

pytestmark = pytest.mark.django_db


def pay(tenant, amount, withholding="0", method=Payment.METHOD_MPESA, **kwargs):
    return record_payment(
        tenant=tenant,
        date_received=timezone.localdate(),
        method=method,
        amount=Decimal(str(amount)),
        withholding_amount=Decimal(str(withholding)),
        **kwargs,
    )


def test_exact_payment_settles_invoice(invoice):
    payment = pay(invoice.tenant, "1000.00")
    assert payment.receipt_number == "RCT-A01-0001"
    allocation = payment.allocations.get()
    assert allocation.invoice == invoice
    assert allocation.amount == Decimal("1000.00")
    assert invoice.balance == Decimal("0.00")
    assert invoice.payment_status == "paid"
    assert invoice.amount_paid == Decimal("1000.00")


def test_partial_payment(invoice):
    payment = pay(invoice.tenant, "400.00")
    assert payment.allocations.get().amount == Decimal("400.00")
    assert invoice.balance == Decimal("600.00")
    assert invoice.payment_status == "partial"


def test_advance_payment_becomes_credit(lease):
    payment = pay(lease.tenant, "1500.00")
    assert not payment.allocations.exists()
    entry = payment.credit_entries.get()
    assert entry.amount == Decimal("1500.00")
    assert entry.source == CreditEntry.SOURCE_OVERPAYMENT
    assert lease.tenant.credit_balance == Decimal("1500.00")


def test_multi_invoice_payment_oldest_first(invoice, older_invoice):
    payment = pay(invoice.tenant, "1300.00")
    allocations = payment.allocations.select_related("invoice").order_by("id")
    assert allocations[0].invoice == older_invoice
    assert allocations[0].amount == Decimal("1000.00")
    assert allocations[1].invoice == invoice
    assert allocations[1].amount == Decimal("300.00")
    assert older_invoice.balance == Decimal("0.00")
    assert invoice.balance == Decimal("700.00")


def test_overpayment_creates_credit(invoice):
    payment = pay(invoice.tenant, "1800.00")
    assert invoice.balance == Decimal("0.00")
    assert payment.credit_entries.get().amount == Decimal("800.00")
    assert invoice.tenant.credit_balance == Decimal("800.00")


def test_manual_allocation_override(invoice, older_invoice):
    payment = pay(
        invoice.tenant,
        "1500.00",
        manual_allocations={
            invoice.pk: "500.00",
            older_invoice.pk: "1000.00",
        },
    )
    allocations = {
        allocation.invoice_id: allocation
        for allocation in payment.allocations.all()
    }
    assert allocations[older_invoice.pk].amount == Decimal("1000.00")
    assert allocations[invoice.pk].amount == Decimal("500.00")
    assert allocations[invoice.pk].is_auto is False
    assert older_invoice.balance == Decimal("0.00")
    assert invoice.balance == Decimal("500.00")


def test_manual_allocation_cannot_exceed_settlement(invoice, older_invoice):
    with pytest.raises(ValidationError):
        pay(
            invoice.tenant,
            "500.00",
            manual_allocations={invoice.pk: "1000.00"},
        )


def test_manual_allocation_cannot_exceed_invoice_balance(invoice):
    with pytest.raises(ValidationError):
        pay(
            invoice.tenant,
            "1500.00",
            manual_allocations={invoice.pk: "1500.00"},
        )


def test_withholding_together_with_cash_settles_invoice(invoice):
    payment = pay(invoice.tenant, "900.00", withholding="100.00")
    assert payment.amount == Decimal("900.00")
    assert payment.withholding_amount == Decimal("100.00")
    assert payment.settlement_amount == Decimal("1000.00")
    assert payment.allocations.get().amount == Decimal("1000.00")
    assert invoice.balance == Decimal("0.00")


def test_withholding_only_payment(invoice):
    payment = pay(invoice.tenant, "0", withholding="1000.00")
    assert payment.settlement_amount == Decimal("1000.00")
    assert invoice.balance == Decimal("0.00")


def test_credit_is_applied_to_next_invoice(invoice):
    pay(invoice.tenant, "1300.00")
    assert invoice.tenant.credit_balance == Decimal("300.00")

    today = timezone.localdate()
    start = add_months(today.replace(day=1), 1)
    end = add_months(today.replace(day=1), 2) - timedelta(days=1)
    next_invoice, _ = generate_invoice(
        invoice.lease, start, end, today + timedelta(days=40)
    )

    assert next_invoice.total == Decimal("1000.00")
    assert next_invoice.amount_paid == Decimal("300.00")
    assert next_invoice.balance == Decimal("700.00")
    assert invoice.tenant.credit_balance == Decimal("0.00")
    applied = next_invoice.credit_entries.get(source=CreditEntry.SOURCE_APPLIED)
    assert applied.amount == Decimal("-300.00")

    pay(invoice.tenant, "700.00")
    assert next_invoice.balance == Decimal("0.00")


def test_cheque_banked_then_bounced_reverses(invoice):
    payment = pay(invoice.tenant, "1000.00", method=Payment.METHOD_CHEQUE)
    assert invoice.balance == Decimal("0.00")

    mark_cheque_banked(payment)
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_POSTED
    assert payment.cheque_status == Payment.CHEQUE_BANKED

    mark_cheque_bounced(payment)
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_VOID
    assert payment.cheque_status == Payment.CHEQUE_BOUNCED
    assert invoice.balance == Decimal("1000.00")
    assert invoice.amount_paid == Decimal("0.00")
    assert AuditLog.objects.filter(action="void", model="payments.Payment").exists()


def test_bounced_overpayment_reverses_credit(invoice):
    payment = pay(invoice.tenant, "1200.00", method=Payment.METHOD_CHEQUE)
    assert invoice.tenant.credit_balance == Decimal("200.00")
    mark_cheque_bounced(payment)
    assert invoice.tenant.credit_balance == Decimal("0.00")
    assert invoice.balance == Decimal("1000.00")


def test_void_payment_restores_balance(invoice):
    payment = pay(invoice.tenant, "1000.00")
    assert invoice.balance == Decimal("0.00")
    void_payment(payment, reason="Recorded in error")
    payment.refresh_from_db()
    assert payment.status == Payment.STATUS_VOID
    assert invoice.balance == Decimal("1000.00")
    assert PaymentAllocation.objects.filter(payment=payment).count() == 1


def test_payment_status_overdue(older_invoice):
    assert older_invoice.payment_status == "overdue"
    pay(older_invoice.tenant, "400.00")
    assert older_invoice.payment_status == "overdue"


def test_receipt_numbering_is_per_unit(lease, unit, building, floor):
    first = pay(lease.tenant, "100.00")
    second = pay(lease.tenant, "100.00")
    assert first.receipt_number == "RCT-A01-0001"
    assert second.receipt_number == "RCT-A01-0002"

    other_tenant = Tenant.objects.create(business_name="Salon Bella")
    other_unit = Unit.objects.create(
        building=building, floor=floor, code="B01", base_rent=Decimal("1000")
    )
    other_tenant.primary_unit = other_unit
    other_tenant.save()
    third = pay(other_tenant, "100.00")
    assert third.receipt_number == "RCT-B01-0001"


def test_payment_requires_a_unit_for_numbering():
    tenant = Tenant.objects.create(business_name="No Unit Ltd")
    with pytest.raises(ValidationError):
        pay(tenant, "100.00")


def test_payment_requires_positive_settlement(invoice):
    with pytest.raises(ValidationError):
        pay(invoice.tenant, "0", withholding="0")
