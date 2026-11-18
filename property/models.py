"""Property, tenant and lease models.

Field names, statuses and rules follow docs/SCHEMA.md. Unit status is kept in
sync from active leases by the service layer and signals.
"""

from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel, get_current_user


class Building(TimeStampedModel):
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class Floor(TimeStampedModel):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="floors")
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["building__name", "sort_order", "name", "id"]

    def __str__(self):
        return f"{self.building.name} - {self.name}"


class Unit(TimeStampedModel):
    STATUS_VACANT = "vacant"
    STATUS_OCCUPIED = "occupied"
    STATUS_RESERVED = "reserved"
    STATUS_CHOICES = [
        (STATUS_VACANT, "Vacant"),
        (STATUS_OCCUPIED, "Occupied"),
        (STATUS_RESERVED, "Reserved"),
    ]

    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name="units")
    floor = models.ForeignKey(Floor, on_delete=models.PROTECT, related_name="units")
    code = models.CharField(max_length=20, unique=True)
    size_sqm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    base_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VACANT)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return self.code

    def clean(self):
        if self.building_id and self.floor_id and self.floor.building_id != self.building_id:
            raise ValidationError({"floor": "The floor must belong to the selected building."})

    @property
    def active_lease(self):
        from django.utils import timezone

        today = timezone.localdate()
        return (
            self.leases.filter(
                status=Lease.STATUS_ACTIVE,
                start_date__lte=today,
                end_date__gte=today,
            )
            .select_related("tenant")
            .first()
        )


class Tenant(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_FORMER = "former"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_FORMER, "Former"),
    ]

    business_name = models.CharField(max_length=200)
    trade = models.CharField(max_length=150, blank=True)
    id_or_kra_pin = models.CharField(max_length=50, blank=True)
    permit_number = models.CharField(max_length=50, blank=True)
    vat_applicable = models.BooleanField(default=False)
    withholding_applicable = models.BooleanField(default=False)
    primary_unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="tenants"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["business_name"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return self.business_name

    @property
    def primary_contact(self):
        return self.contacts.filter(is_primary=True).first() or self.contacts.first()

    @property
    def current_lease(self):
        from django.utils import timezone

        today = timezone.localdate()
        return (
            self.leases.filter(
                status=Lease.STATUS_ACTIVE,
                start_date__lte=today,
                end_date__gte=today,
            )
            .select_related("unit")
            .first()
        )


class TenantContact(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=150)
    role_title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]

    def __str__(self):
        return f"{self.name} ({self.tenant.business_name})"

    def save(self, *args, **kwargs):
        if self.is_primary and self.tenant_id:
            others = TenantContact.objects.filter(
                tenant_id=self.tenant_id, is_primary=True
            ).exclude(pk=self.pk)
            for other in others:
                other.is_primary = False
                other.save(update_fields=["is_primary", "updated_at"])
        super().save(*args, **kwargs)


class Document(TimeStampedModel):
    DOC_TYPE_CHOICES = [
        ("lease", "Lease"),
        ("id_copy", "ID copy"),
        ("permit", "Permit"),
        ("receipt", "Receipt"),
        ("photo", "Photo"),
        ("other", "Other"),
    ]

    owner_type = models.ForeignKey(
        ContentType, on_delete=models.PROTECT, related_name="+"
    )
    owner_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("owner_type", "owner_id")
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    file = models.FileField(upload_to="documents/%Y/%m/")
    uploaded_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        indexes = [models.Index(fields=["owner_type", "owner_id"])]

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.file.name}"

    def save(self, *args, **kwargs):
        if self.uploaded_by_id is None:
            self.uploaded_by = get_current_user()
        super().save(*args, **kwargs)


class Lease(TimeStampedModel):
    ESCALATION_NONE = "none"
    ESCALATION_PERCENT = "percent"
    ESCALATION_FIXED = "fixed"
    ESCALATION_CHOICES = [
        (ESCALATION_NONE, "None"),
        (ESCALATION_PERCENT, "Percentage"),
        (ESCALATION_FIXED, "Fixed amount"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_TERMINATED = "terminated"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_TERMINATED, "Terminated"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="leases")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="leases")
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    escalation_type = models.CharField(
        max_length=20, choices=ESCALATION_CHOICES, default=ESCALATION_NONE
    )
    escalation_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    escalation_interval_months = models.PositiveSmallIntegerField(null=True, blank=True)
    next_escalation_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    terminated_on = models.DateField(null=True, blank=True)
    termination_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["unit", "status"]),
            models.Index(fields=["end_date"]),
        ]

    def __str__(self):
        return f"{self.tenant.business_name} - {self.unit.code}"

    def clean(self):
        from property.services import validate_lease_fields

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})

        validate_lease_fields(
            escalation_type=self.escalation_type,
            escalation_value=self.escalation_value,
            escalation_interval_months=self.escalation_interval_months,
            next_escalation_date=self.next_escalation_date,
        )

        if self.status == self.STATUS_ACTIVE and self.unit_id and self.start_date and self.end_date:
            overlapping = (
                Lease.objects.filter(
                    unit_id=self.unit_id,
                    status=self.STATUS_ACTIVE,
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                )
                .exclude(pk=self.pk)
                .select_related("tenant")
            )
            if overlapping.exists():
                other = overlapping.first()
                raise ValidationError(
                    {
                        "unit": (
                            f"This unit already has an active lease with {other.tenant.business_name} "
                            f"from {other.start_date:%d %b %Y} to {other.end_date:%d %b %Y}."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        if self.escalation_type == self.ESCALATION_NONE:
            self.escalation_value = Decimal("0.00")
            self.escalation_interval_months = None
            self.next_escalation_date = None
        super().save(*args, **kwargs)
        if self.tenant_id and self.unit_id and self.tenant.primary_unit_id is None:
            self.tenant.primary_unit = self.unit
            self.tenant.save(update_fields=["primary_unit", "updated_at"])


class LeaseRentHistory(TimeStampedModel):
    REASON_INITIAL = "initial"
    REASON_ESCALATION = "escalation"
    REASON_MANUAL = "manual"
    REASON_CHOICES = [
        (REASON_INITIAL, "Initial rent"),
        (REASON_ESCALATION, "Escalation"),
        (REASON_MANUAL, "Manual change"),
    ]

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="rent_history")
    effective_date = models.DateField()
    old_rent = models.DecimalField(max_digits=12, decimal_places=2)
    new_rent = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    changed_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-effective_date", "-id"]

    def __str__(self):
        return f"{self.lease} rent {self.old_rent} -> {self.new_rent}"
