"""Operations models: deposits, move-outs, prospects, maintenance and expenses."""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel


class Deposit(TimeStampedModel):
    STATUS_HELD = "held"
    STATUS_PARTLY_REFUNDED = "partly_refunded"
    STATUS_REFUNDED = "refunded"
    STATUS_FORFEITED = "forfeited"
    STATUS_CHOICES = [
        (STATUS_HELD, "Held"),
        (STATUS_PARTLY_REFUNDED, "Partly refunded"),
        (STATUS_REFUNDED, "Refunded"),
        (STATUS_FORFEITED, "Forfeited"),
    ]

    lease = models.ForeignKey(
        "property.Lease", on_delete=models.PROTECT, related_name="deposits"
    )
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    received_date = models.DateField()
    payment = models.ForeignKey(
        "payments.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_HELD)

    class Meta:
        ordering = ["received_date", "id"]

    def __str__(self):
        return f"{self.lease.unit.code} deposit {self.amount_received}"


class MoveOut(TimeStampedModel):
    STATUS_PLANNED = "planned"
    STATUS_SETTLED = "settled"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planned"),
        (STATUS_SETTLED, "Settled"),
    ]

    lease = models.ForeignKey(
        "property.Lease", on_delete=models.PROTECT, related_name="move_outs"
    )
    notice_date = models.DateField(null=True, blank=True)
    move_out_date = models.DateField()
    arrears_at_exit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    damages_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deposit_held = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED
    )
    settlement_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-move_out_date", "-id"]
        indexes = [models.Index(fields=["lease", "status"])]

    def __str__(self):
        return f"Move-out {self.lease.unit.code} {self.move_out_date}"

    @property
    def remaining_balance(self):
        value = (
            (self.arrears_at_exit or Decimal("0"))
            + (self.damages_amount or Decimal("0"))
            - (self.deposit_held or Decimal("0"))
        )
        return value if value > 0 else Decimal("0.00")


class MoveOutItem(TimeStampedModel):
    ITEM_DOOR = "door"
    ITEM_SHUTTER = "shutter"
    ITEM_LIGHTS = "lights"
    ITEM_FLOOR = "floor"
    ITEM_METER = "meter"
    ITEM_CHOICES = [
        (ITEM_DOOR, "Door"),
        (ITEM_SHUTTER, "Shutter"),
        (ITEM_LIGHTS, "Lights"),
        (ITEM_FLOOR, "Floor"),
        (ITEM_METER, "Meter"),
    ]

    move_out = models.ForeignKey(
        MoveOut, on_delete=models.CASCADE, related_name="items"
    )
    item = models.CharField(max_length=20, choices=ITEM_CHOICES)
    condition = models.CharField(max_length=50, default="ok")
    damage_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["item", "id"]

    def __str__(self):
        return f"{self.get_item_display()} - {self.condition}"


class Prospect(TimeStampedModel):
    STATUS_NEW = "new"
    STATUS_VIEWING = "viewing"
    STATUS_NEGOTIATING = "negotiating"
    STATUS_CONVERTED = "converted"
    STATUS_LOST = "lost"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_VIEWING, "Viewing"),
        (STATUS_NEGOTIATING, "Negotiating"),
        (STATUS_CONVERTED, "Converted"),
        (STATUS_LOST, "Lost"),
    ]

    name = models.CharField(max_length=150)
    business = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    interested_unit = models.ForeignKey(
        "property.Unit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prospects",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    converted_lease = models.ForeignKey(
        "property.Lease",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prospect_conversions",
    )

    class Meta:
        ordering = ["follow_up_date", "name"]
        indexes = [models.Index(fields=["status", "follow_up_date"])]

    def __str__(self):
        return self.business or self.name


class MaintenanceRequest(TimeStampedModel):
    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_DONE, "Done"),
    ]

    unit = models.ForeignKey(
        "property.Unit", on_delete=models.PROTECT, related_name="maintenance_requests"
    )
    tenant = models.ForeignKey(
        "property.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_requests",
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    reported_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    expense = models.ForeignKey(
        "operations.Expense",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-reported_date", "-id"]
        indexes = [models.Index(fields=["status", "priority"])]

    def __str__(self):
        return self.title


class ExpenseCategory(TimeStampedModel):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    PAYMENT_CHOICES = [
        ("mpesa", "M-Pesa"),
        ("bank", "Bank"),
        ("cash", "Cash"),
        ("cheque", "Cheque"),
        ("other", "Other"),
    ]

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    expense_date = models.DateField()
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    payee = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, blank=True
    )
    reference = models.CharField(max_length=100, blank=True)
    maintenance_request = models.ForeignKey(
        MaintenanceRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )

    class Meta:
        ordering = ["-expense_date", "-id"]
        indexes = [models.Index(fields=["category", "expense_date"])]

    def __str__(self):
        return f"{self.payee} {self.amount}"
