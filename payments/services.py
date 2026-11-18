"""Payment allocation, credit application and cheque lifecycle."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from billing.models import Invoice
from core.models import AuditLog, NumberSequence, Settings
from core.numbering import next_document_number
from payments.models import CreditEntry, Payment, PaymentAllocation


def invoice_balance(invoice: Invoice) -> Decimal:
    return invoice.balance


def open_invoices(tenant):
    return (
        Invoice.objects.filter(tenant=tenant, status=Invoice.STATUS_ISSUED)
        .select_related("unit")
        .order_by("due_date", "issue_date", "id")
    )


def suggest_allocations(tenant, settlement_amount: Decimal):
    """Oldest due invoice first. Returns (rows, credit_remainder)."""
    remaining = Decimal(settlement_amount)
    rows = []
    for invoice in open_invoices(tenant):
        if remaining <= 0:
            break
        balance = invoice.balance
        if balance <= 0:
            continue
        amount = min(remaining, balance)
        rows.append({"invoice": invoice, "amount": amount})
        remaining -= amount
    return rows, remaining


def _unit_for_receipt(tenant, allocation_rows):
    if tenant.primary_unit_id:
        return tenant.primary_unit
    for row in allocation_rows:
        if row["invoice"].unit_id:
            return row["invoice"].unit
    return None


def _normalise_manual_allocations(tenant, manual_allocations):
    rows = []
    for invoice_id, raw_amount in manual_allocations.items():
        try:
            amount = Decimal(str(raw_amount or "0"))
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("Allocation amounts must be numbers.") from exc
        if amount < 0:
            raise ValidationError("Allocation amounts cannot be negative.")
        if amount == 0:
            continue
        invoice = (
            Invoice.objects.filter(pk=invoice_id, tenant=tenant, status=Invoice.STATUS_ISSUED)
            .select_related("unit")
            .first()
        )
        if invoice is None:
            raise ValidationError("An allocation points to an invoice that is not this tenant's.")
        if amount > invoice.balance:
            raise ValidationError(
                f"Allocation to {invoice.invoice_number} exceeds its balance of {invoice.balance}."
            )
        rows.append({"invoice": invoice, "amount": amount})
    rows.sort(key=lambda row: (row["invoice"].due_date, row["invoice"].id))
    return rows


def record_payment(
    tenant,
    date_received,
    method,
    amount,
    withholding_amount=Decimal("0.00"),
    reference="",
    cheque_number="",
    cheque_bank="",
    withholding_cert_no="",
    notes="",
    manual_allocations=None,
    statement_row=None,
    user=None,
    cheque_status=Payment.CHEQUE_RECEIVED,
):
    amount = Decimal(str(amount or "0"))
    withholding_amount = Decimal(str(withholding_amount or "0"))
    if amount < 0 or withholding_amount < 0:
        raise ValidationError("Payment amounts cannot be negative.")
    settlement = amount + withholding_amount
    if settlement <= 0:
        raise ValidationError("Enter a payment amount or withholding amount.")

    if manual_allocations is not None:
        allocation_rows = _normalise_manual_allocations(tenant, manual_allocations)
        is_auto = False
    else:
        allocation_rows, _credit = suggest_allocations(tenant, settlement)
        is_auto = True

    allocated_total = sum((row["amount"] for row in allocation_rows), Decimal("0.00"))
    if allocated_total > settlement:
        raise ValidationError("Allocations cannot exceed the payment plus withholding.")
    credit = settlement - allocated_total

    unit = _unit_for_receipt(tenant, allocation_rows)
    if unit is None:
        raise ValidationError(
            "Set a primary unit for this tenant before recording payments without an invoice."
        )

    with transaction.atomic():
        settings_obj = Settings.load()
        receipt_number = next_document_number(
            NumberSequence.DOC_RECEIPT, unit, settings_obj
        )
        payment = Payment.objects.create(
            receipt_number=receipt_number,
            tenant=tenant,
            date_received=date_received,
            method=method,
            amount=amount,
            reference=reference,
            cheque_number=cheque_number,
            cheque_bank=cheque_bank,
            cheque_status=cheque_status if method == Payment.METHOD_CHEQUE else Payment.CHEQUE_RECEIVED,
            withholding_amount=withholding_amount,
            withholding_cert_no=withholding_cert_no,
            status=Payment.STATUS_POSTED,
            notes=notes,
            statement_row=statement_row,
            recorded_by=user,
        )

        for row in allocation_rows:
            PaymentAllocation.objects.create(
                payment=payment,
                invoice=row["invoice"],
                amount=row["amount"],
                is_auto=is_auto,
            )

        if credit > 0:
            CreditEntry.objects.create(
                tenant=tenant,
                entry_date=date_received,
                amount=credit,
                source=CreditEntry.SOURCE_OVERPAYMENT,
                payment=payment,
            )

        if statement_row is not None:
            statement_row.payment = payment
            statement_row.match_status = statement_row.MATCH_CONFIRMED
            statement_row.save(
                update_fields=["payment", "match_status", "updated_at"]
            )

    return payment


def active_credits(tenant):
    return CreditEntry.objects.filter(tenant=tenant).filter(
        Q(payment__isnull=True) | Q(payment__status=Payment.STATUS_POSTED)
    )


def credit_balance(tenant) -> Decimal:
    value = active_credits(tenant).aggregate(total=Sum("amount"))["total"]
    return value or Decimal("0.00")


def apply_credit_to_invoice(invoice: Invoice) -> Decimal:
    """Apply available tenant credit to a newly generated invoice."""
    if invoice.balance <= 0:
        return Decimal("0.00")

    groups = (
        active_credits(invoice.tenant)
        .values("payment_id")
        .annotate(balance=Sum("amount"))
        .filter(balance__gt=0)
        .order_by("payment_id")
    )

    total_applied = Decimal("0.00")
    for group in groups:
        if invoice.balance <= 0:
            break
        available = Decimal(group["balance"])
        applied = min(available, invoice.balance)
        if applied <= 0:
            continue
        CreditEntry.objects.create(
            tenant=invoice.tenant,
            entry_date=timezone.localdate(),
            amount=-applied,
            source=CreditEntry.SOURCE_APPLIED,
            payment_id=group["payment_id"],
            invoice=invoice,
        )
        total_applied += applied
        invoice = Invoice.objects.get(pk=invoice.pk)
    return total_applied


def void_payment(payment: Payment, reason="", user=None, cheque_bounced=False):
    if payment.status == Payment.STATUS_VOID:
        return payment
    previous_status = payment.status
    payment.status = Payment.STATUS_VOID
    if cheque_bounced:
        payment.cheque_status = Payment.CHEQUE_BOUNCED
    if reason:
        payment.notes = (payment.notes + "\n" + reason).strip()
    payment.save(
        update_fields=["status", "cheque_status", "notes", "updated_at"]
    )
    AuditLog.objects.create(
        user=user,
        action="void",
        model="payments.Payment",
        object_id=str(payment.pk),
        object_repr=str(payment)[:255],
        changes={
            "before": {"status": previous_status},
            "after": {
                "status": payment.status,
                "cheque_status": payment.cheque_status,
                "reason": reason,
            },
        },
    )
    return payment


def mark_cheque_banked(payment: Payment, user=None):
    if payment.method != Payment.METHOD_CHEQUE:
        raise ValidationError("Only cheque payments have a cheque status.")
    payment.cheque_status = Payment.CHEQUE_BANKED
    payment.save(update_fields=["cheque_status", "updated_at"])
    return payment


def mark_cheque_bounced(payment: Payment, user=None, reason="Cheque bounced"):
    if payment.method != Payment.METHOD_CHEQUE:
        raise ValidationError("Only cheque payments have a cheque status.")
    return void_payment(payment, reason=reason, user=user, cheque_bounced=True)
