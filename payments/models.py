"""Payments, allocations, credit and statement imports."""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Payment(TimeStampedModel):
    METHOD_MPESA = "mpesa"
    METHOD_BANK = "bank"
    METHOD_CASH = "cash"
    METHOD_CHEQUE = "cheque"
    METHOD_CHOICES = [
        (METHOD_MPESA, "M-Pesa"),
        (METHOD_BANK, "Bank deposit"),
        (METHOD_CASH, "Cash"),
        (METHOD_CHEQUE, "Cheque"),
    ]
    ENTRY_METHOD_CHOICES = [(METHOD_BANK, "Bank deposit")]

    CHEQUE_RECEIVED = "received"
    CHEQUE_BANKED = "banked"
    CHEQUE_BOUNCED = "bounced"
    CHEQUE_STATUS_CHOICES = [
        (CHEQUE_RECEIVED, "Received"),
        (CHEQUE_BANKED, "Banked"),
        (CHEQUE_BOUNCED, "Bounced"),
    ]

    STATUS_POSTED = "posted"
    STATUS_VOID = "void"
    STATUS_CHOICES = [
        (STATUS_POSTED, "Posted"),
        (STATUS_VOID, "Void"),
    ]

    receipt_number = models.CharField(max_length=50, unique=True)
    tenant = models.ForeignKey(
        "property.Tenant", on_delete=models.PROTECT, related_name="payments"
    )
    date_received = models.DateField()
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    reference = models.CharField(max_length=100, blank=True)
    cheque_number = models.CharField(max_length=50, blank=True)
    cheque_bank = models.CharField(max_length=100, blank=True)
    cheque_status = models.CharField(
        max_length=20, choices=CHEQUE_STATUS_CHOICES, default=CHEQUE_RECEIVED
    )
    withholding_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    withholding_cert_no = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_POSTED)
    notes = models.TextField(blank=True)
    statement_row = models.ForeignKey(
        "payments.StatementRow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    recorded_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-date_received", "-id"]
        indexes = [models.Index(fields=["tenant", "date_received"])]

    def __str__(self):
        return self.receipt_number

    @property
    def is_void(self):
        return self.status == self.STATUS_VOID

    @property
    def settlement_amount(self):
        return (self.amount or Decimal("0")) + (self.withholding_amount or Decimal("0"))

    @property
    def allocated_amount(self):
        return sum(
            (
                allocation.amount
                for allocation in self.allocations.all()
            ),
            Decimal("0.00"),
        )

    @property
    def credit_amount(self):
        from payments.models import CreditEntry

        return sum(
            (
                entry.amount
                for entry in self.credit_entries.filter(source=CreditEntry.SOURCE_OVERPAYMENT)
            ),
            Decimal("0.00"),
        )


class PaymentAllocation(TimeStampedModel):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="allocations"
    )
    invoice = models.ForeignKey(
        "billing.Invoice", on_delete=models.PROTECT, related_name="allocations"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    allocated_at = models.DateTimeField(default=timezone.now)
    is_auto = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["invoice"])]

    def __str__(self):
        return f"{self.payment.receipt_number} -> {self.invoice.invoice_number}"


class CreditEntry(TimeStampedModel):
    SOURCE_OVERPAYMENT = "overpayment"
    SOURCE_APPLIED = "applied_to_invoice"
    SOURCE_REFUND = "refund"
    SOURCE_CHOICES = [
        (SOURCE_OVERPAYMENT, "Overpayment"),
        (SOURCE_APPLIED, "Applied to invoice"),
        (SOURCE_REFUND, "Refund"),
    ]

    tenant = models.ForeignKey(
        "property.Tenant", on_delete=models.PROTECT, related_name="credit_entries"
    )
    entry_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_entries"
    )
    invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_entries"
    )

    class Meta:
        ordering = ["entry_date", "id"]
        indexes = [models.Index(fields=["tenant", "entry_date"])]

    def __str__(self):
        return f"{self.tenant.business_name} credit {self.amount}"


class StatementImport(TimeStampedModel):
    SOURCE_MPESA = "mpesa"
    SOURCE_BANK = "bank"
    SOURCE_CHOICES = [
        (SOURCE_MPESA, "M-Pesa"),
        (SOURCE_BANK, "Bank"),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    file = models.FileField(upload_to="statements/%Y/%m/")
    uploaded_at = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.get_source_display()} import {self.pk}"


class StatementRow(TimeStampedModel):
    MATCH_UNMATCHED = "unmatched"
    MATCH_SUGGESTED = "suggested"
    MATCH_CONFIRMED = "confirmed"
    MATCH_IGNORED = "ignored"
    MATCH_STATUS_CHOICES = [
        (MATCH_UNMATCHED, "Unmatched"),
        (MATCH_SUGGESTED, "Suggested"),
        (MATCH_CONFIRMED, "Confirmed"),
        (MATCH_IGNORED, "Ignored"),
    ]

    import_run = models.ForeignKey(
        StatementImport,
        on_delete=models.CASCADE,
        related_name="rows",
        db_column="import_id",
    )
    tx_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True)
    payer_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    suggested_tenant = models.ForeignKey(
        "property.Tenant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    suggested_invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    match_status = models.CharField(
        max_length=20, choices=MATCH_STATUS_CHOICES, default=MATCH_UNMATCHED
    )
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["tx_date", "id"]
        indexes = [models.Index(fields=["match_status"])]

    def __str__(self):
        return f"{self.tx_date} {self.amount} {self.reference}"
