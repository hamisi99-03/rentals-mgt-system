"""Billing models: charges, invoices, lines and utility readings."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Prefetch, Q
from django.utils import timezone

from core.models import TimeStampedModel


class ChargeType(TimeStampedModel):
    KIND_SERVICE = "service"
    KIND_UTILITY = "utility"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_SERVICE, "Service"),
        (KIND_UTILITY, "Utility"),
        (KIND_OTHER, "Other"),
    ]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_SERVICE)
    vat_applicable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeaseCharge(TimeStampedModel):
    FREQUENCY_MONTHLY = "monthly"
    FREQUENCY_QUARTERLY = "quarterly"
    FREQUENCY_ONCE = "once"
    FREQUENCY_CHOICES = [
        (FREQUENCY_MONTHLY, "Monthly"),
        (FREQUENCY_QUARTERLY, "Quarterly"),
        (FREQUENCY_ONCE, "Once"),
    ]

    lease = models.ForeignKey(
        "property.Lease", on_delete=models.CASCADE, related_name="charges"
    )
    charge_type = models.ForeignKey(
        ChargeType, on_delete=models.PROTECT, related_name="lease_charges"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default=FREQUENCY_MONTHLY
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["charge_type__name", "id"]

    def __str__(self):
        return f"{self.charge_type.name} on {self.lease.unit.code}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})


class Invoice(TimeStampedModel):
    STATUS_ISSUED = "issued"
    STATUS_VOID = "void"
    STATUS_CHOICES = [
        (STATUS_ISSUED, "Issued"),
        (STATUS_VOID, "Void"),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    tenant = models.ForeignKey(
        "property.Tenant", on_delete=models.PROTECT, related_name="invoices"
    )
    lease = models.ForeignKey(
        "property.Lease", on_delete=models.PROTECT, related_name="invoices"
    )
    unit = models.ForeignKey(
        "property.Unit", on_delete=models.PROTECT, related_name="invoices"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    issue_date = models.DateField()
    due_date = models.DateField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_enabled_snapshot = models.BooleanField(default=False)
    vat_rate_snapshot = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ISSUED
    )
    void_reason = models.TextField(blank=True)
    voided_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lease", "period_start"], name="unique_invoice_lease_period"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "due_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.invoice_number

    @property
    def is_void(self):
        return self.status == self.STATUS_VOID

    @property
    def allocated_amount(self):
        cached = getattr(self, "_prefetched_objects_cache", {}).get("allocations")
        if cached is not None:
            return sum(
                (allocation.amount for allocation in cached if allocation.payment.status == "posted"),
                Decimal("0.00"),
            )
        return sum(
            (
                allocation.amount
                for allocation in self.allocations.filter(payment__status="posted")
            ),
            Decimal("0.00"),
        )

    @property
    def credit_applied(self):
        from payments.models import CreditEntry

        cached = getattr(self, "_prefetched_objects_cache", {}).get("credit_entries")
        if cached is None:
            cached = self.credit_entries.filter(
                source=CreditEntry.SOURCE_APPLIED,
            ).filter(Q(payment__isnull=True) | Q(payment__status="posted"))
        value = sum(
            (
                entry.amount
                for entry in cached
                if entry.source == CreditEntry.SOURCE_APPLIED
                and (entry.payment_id is None or entry.payment.status == "posted")
            ),
            Decimal("0.00"),
        )
        return -value

    @property
    def amount_paid(self):
        return self.allocated_amount + self.credit_applied

    @property
    def balance(self):
        remaining = self.total - self.amount_paid
        return remaining if remaining > 0 else Decimal("0.00")

    @property
    def payment_status(self):
        if self.balance <= 0:
            return "paid"
        if self.due_date and self.due_date < timezone.localdate():
            return "overdue"
        if self.amount_paid > 0:
            return "partial"
        return "unpaid"


class InvoiceLine(TimeStampedModel):
    KIND_RENT = "rent"
    KIND_SERVICE = "service"
    KIND_UTILITY = "utility"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_RENT, "Rent"),
        (KIND_SERVICE, "Service"),
        (KIND_UTILITY, "Utility"),
        (KIND_OTHER, "Other"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    charge_type = models.ForeignKey(
        ChargeType, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} ({self.amount})"


class UtilityType(TimeStampedModel):
    name = models.CharField(max_length=100)
    measure = models.CharField(
        max_length=20, default="m3", help_text="e.g. m3, kWh or kg"
    )
    rate_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.measure})"


class MeterReading(TimeStampedModel):
    unit = models.ForeignKey(
        "property.Unit", on_delete=models.PROTECT, related_name="meter_readings"
    )
    utility_type = models.ForeignKey(
        UtilityType, on_delete=models.PROTECT, related_name="meter_readings"
    )
    reading_date = models.DateField()
    reading_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    previous_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    consumption = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    invoice_line = models.ForeignKey(
        InvoiceLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meter_readings",
    )

    class Meta:
        ordering = ["-reading_date", "-id"]
        unique_together = [("unit", "utility_type", "reading_date")]

    def __str__(self):
        return f"{self.unit.code} {self.utility_type.name} {self.reading_date}"

    @property
    def charge_amount(self):
        return (self.consumption * self.utility_type.rate_per_unit).quantize(
            Decimal("0.01")
        )

    def clean(self):
        if (
            self.reading_value is not None
            and self.previous_value is not None
            and self.reading_value < self.previous_value
        ):
            raise ValidationError(
                {"reading_value": "The reading cannot be lower than the previous reading."}
            )

    def save(self, *args, **kwargs):
        if self.unit_id and self.utility_type_id and self.reading_date:
            previous = (
                MeterReading.objects.filter(
                    unit_id=self.unit_id,
                    utility_type_id=self.utility_type_id,
                    reading_date__lt=self.reading_date,
                )
                .exclude(pk=self.pk)
                .order_by("-reading_date", "-id")
                .first()
            )
            self.previous_value = (
                previous.reading_value if previous else Decimal("0.00")
            )
            self.consumption = self.reading_value - self.previous_value
        super().save(*args, **kwargs)


def with_balances(queryset):
    """Prefetch allocations and credit entries so invoice balances avoid N+1 queries."""
    from payments.models import CreditEntry, PaymentAllocation

    return queryset.prefetch_related(
        Prefetch(
            "allocations",
            queryset=PaymentAllocation.objects.select_related("payment"),
        ),
        Prefetch(
            "credit_entries",
            queryset=CreditEntry.objects.select_related("payment"),
        ),
    )
