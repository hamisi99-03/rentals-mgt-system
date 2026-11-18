"""Business rules for leases and unit occupancy."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from property.models import Lease, LeaseRentHistory, Unit


def validate_lease_fields(
    escalation_type: str,
    escalation_value,
    escalation_interval_months,
    next_escalation_date,
):
    """Shared escalation validation used by the model, forms and importer."""
    if escalation_type in (None, "", Lease.ESCALATION_NONE):
        return

    value = Decimal(str(escalation_value or "0"))
    if escalation_type == Lease.ESCALATION_PERCENT:
        if not (Decimal("0") < value <= Decimal("100")):
            raise ValidationError(
                {"escalation_value": "Percentage escalation must be above 0 and at most 100."}
            )
    elif escalation_type == Lease.ESCALATION_FIXED:
        if value <= 0:
            raise ValidationError(
                {"escalation_value": "Fixed escalation must be greater than 0."}
            )
    else:
        raise ValidationError({"escalation_type": "Unknown escalation type."})

    if not escalation_interval_months or escalation_interval_months < 1:
        raise ValidationError(
            {"escalation_interval_months": "Set the escalation interval in months."}
        )
    if not next_escalation_date:
        raise ValidationError(
            {"next_escalation_date": "Set the next escalation date."}
        )


def has_active_lease(unit, on_date=None) -> bool:
    on_date = on_date or timezone.localdate()
    return Lease.objects.filter(
        unit=unit,
        status=Lease.STATUS_ACTIVE,
        start_date__lte=on_date,
        end_date__gte=on_date,
    ).exists()


def current_lease(unit, on_date=None):
    on_date = on_date or timezone.localdate()
    return (
        Lease.objects.filter(
            unit=unit,
            status=Lease.STATUS_ACTIVE,
            start_date__lte=on_date,
            end_date__gte=on_date,
        )
        .select_related("tenant")
        .first()
    )


def sync_unit_status(unit) -> str:
    """Derive occupancy from leases, preserving a manual reserved flag."""
    if has_active_lease(unit):
        desired = Unit.STATUS_OCCUPIED
    elif unit.status == Unit.STATUS_OCCUPIED:
        desired = Unit.STATUS_VACANT
    else:
        desired = unit.status

    if desired != unit.status:
        unit.status = desired
        unit.save(update_fields=["status", "updated_at"])
    return unit.status


def refresh_unit_statuses():
    today = timezone.localdate()
    active_unit_ids = set(
        Lease.objects.filter(
            status=Lease.STATUS_ACTIVE,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list("unit_id", flat=True)
    )
    for unit in Unit.objects.all():
        if unit.pk in active_unit_ids:
            desired = Unit.STATUS_OCCUPIED
        elif unit.status == Unit.STATUS_OCCUPIED:
            desired = Unit.STATUS_VACANT
        else:
            desired = unit.status
        if desired != unit.status:
            unit.status = desired
            unit.save(update_fields=["status", "updated_at"])


def refresh_lease_statuses():
    """Expire leases whose end date has passed, then refresh unit occupancy."""
    today = timezone.localdate()
    expired = Lease.objects.filter(status=Lease.STATUS_ACTIVE, end_date__lt=today)
    for lease in expired:
        lease.status = Lease.STATUS_EXPIRED
        lease.save(update_fields=["status", "updated_at"])
    refresh_unit_statuses()


def record_initial_rent(lease, changed_by=None):
    return LeaseRentHistory.objects.create(
        lease=lease,
        effective_date=lease.start_date,
        old_rent=Decimal("0.00"),
        new_rent=lease.monthly_rent,
        reason=LeaseRentHistory.REASON_INITIAL,
        changed_by=changed_by,
    )


def record_rent_change(lease, old_rent, changed_by=None):
    return LeaseRentHistory.objects.create(
        lease=lease,
        effective_date=timezone.localdate(),
        old_rent=old_rent,
        new_rent=lease.monthly_rent,
        reason=LeaseRentHistory.REASON_MANUAL,
        changed_by=changed_by,
    )
