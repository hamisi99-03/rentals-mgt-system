"""Core models: users, application settings, audit trail and backup log."""

from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}){1,2}$",
    message="Enter a colour as a hex value, for example #1D4ED8.",
)


def get_current_user():
    """Return the user attached to the current request, if any."""
    from core.middleware import get_current_user as _get

    return _get()


class TimeStampedModel(models.Model):
    """Common audit columns required on every business table."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.created_by_id is None:
            self.created_by = get_current_user()
        super().save(*args, **kwargs)


class User(AbstractUser):
    MODE_LIGHT = "light"
    MODE_DARK = "dark"
    MODE_SYSTEM = "system"
    MODE_CHOICES = [
        (MODE_LIGHT, "Light"),
        (MODE_DARK, "Dark"),
        (MODE_SYSTEM, "Match Windows"),
    ]

    PALETTE_CHOICES = [
        ("ocean", "Ocean"),
        ("forest", "Forest"),
        ("sunset", "Sunset"),
        ("slate", "Slate"),
        ("plum", "Plum"),
    ]

    DENSITY_CHOICES = [
        ("comfortable", "Comfortable"),
        ("compact", "Compact"),
    ]

    TEXT_SIZE_CHOICES = [
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
    ]

    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    auto_lock_minutes = models.PositiveSmallIntegerField(
        default=15, validators=[MinValueValidator(1), MaxValueValidator(240)]
    )

    theme_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_SYSTEM)
    theme_palette = models.CharField(max_length=20, choices=PALETTE_CHOICES, default="ocean")
    theme_density = models.CharField(
        max_length=20, choices=DENSITY_CHOICES, default="comfortable"
    )
    theme_text_size = models.CharField(
        max_length=10, choices=TEXT_SIZE_CHOICES, default="medium"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def __str__(self):
        return self.full_name or self.username

    @property
    def display_name(self):
        return self.full_name or self.username


class Settings(TimeStampedModel):
    """Single-row application settings. Tax rates and numbering live here, not in code."""

    company_name = models.CharField(max_length=150, default="Rental Manager")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    kra_pin = models.CharField(max_length=30, blank=True)
    logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    letterhead_text = models.TextField(blank=True)
    currency = models.CharField(max_length=10, default="KES")
    service_charge_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("500.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=(
            "Fixed monthly charge covering water, electricity, security and toilet, "
            "added to every new lease."
        ),
    )

    vat_enabled = models.BooleanField(default=False)
    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("16.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    withholding_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    invoice_prefix = models.CharField(max_length=10, default="INV")
    receipt_prefix = models.CharField(max_length=10, default="RCT")
    number_separator = models.CharField(max_length=3, default="-")
    number_padding = models.PositiveSmallIntegerField(
        default=4, validators=[MinValueValidator(3), MaxValueValidator(8)]
    )
    invoice_due_day = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(28)]
    )
    renewal_alert_days = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(1), MaxValueValidator(365)]
    )

    backup_folder = models.CharField(max_length=500, blank=True)
    reminder_template = models.TextField(
        default=(
            "Hello {tenant}, this is a friendly reminder that invoice {invoice} for "
            "{unit} is overdue. Outstanding balance: {balance}. Please arrange payment. "
            "Thank you."
        )
    )

    default_palette = models.CharField(
        max_length=20, choices=User.PALETTE_CHOICES, default="ocean"
    )
    brand_color = models.CharField(
        max_length=7, blank=True, validators=[HEX_COLOR_VALIDATOR]
    )

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    def __str__(self):
        return "Application settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Application settings cannot be deleted.")

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def clean(self):
        if self.vat_rate is not None and not (0 <= self.vat_rate <= 100):
            raise ValidationError({"vat_rate": "VAT rate must be between 0 and 100."})
        if self.withholding_rate is not None and not (0 <= self.withholding_rate <= 100):
            raise ValidationError(
                {"withholding_rate": "Withholding rate must be between 0 and 100."}
            )


class AuditLog(models.Model):
    """Append-only activity trail. Never edited or deleted from the app."""

    ACTION_CHOICES = [
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("void", "Void"),
        ("login", "Login"),
        ("backup", "Backup"),
        ("restore", "Restore"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [models.Index(fields=["timestamp"])]

    def __str__(self):
        return f"{self.action} {self.model} {self.object_repr}".strip()

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit log entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries cannot be deleted.")


class BackupLog(models.Model):
    RESULT_CHOICES = [("ok", "OK"), ("failed", "Failed")]

    timestamp = models.DateTimeField(auto_now_add=True)
    destination_path = models.CharField(max_length=500, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self):
        return f"{self.result} {self.destination_path}".strip()


class NumberSequence(TimeStampedModel):
    """Per document type and unit counter. Incremented inside a transaction."""

    DOC_INVOICE = "invoice"
    DOC_RECEIPT = "receipt"
    DOC_TYPE_CHOICES = [
        (DOC_INVOICE, "Invoice"),
        (DOC_RECEIPT, "Receipt"),
    ]

    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    unit = models.ForeignKey(
        "property.Unit", on_delete=models.PROTECT, related_name="number_sequences"
    )
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("doc_type", "unit")]
        ordering = ["doc_type", "unit__code"]

    def __str__(self):
        return f"{self.doc_type} {self.unit.code}: {self.last_value}"
