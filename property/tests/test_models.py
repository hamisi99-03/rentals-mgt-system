from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from property.forms import LeaseForm
from property.models import Lease, LeaseRentHistory, Tenant, TenantContact, Unit
from property.services import (
    refresh_lease_statuses,
    refresh_unit_statuses,
    sync_unit_status,
)

pytestmark = pytest.mark.django_db


def test_unit_requires_matching_building_and_floor(building, floor):
    from property.models import Building as BuildingModel

    other = BuildingModel.objects.create(name="Other building")
    unit = Unit(building=other, floor=floor, code="X01", base_rent=Decimal("1000"))
    with pytest.raises(ValidationError) as error:
        unit.full_clean()
    assert "floor" in error.value.message_dict


def test_unit_code_is_unique(building, floor, unit):
    duplicate = Unit(building=building, floor=floor, code="A01", base_rent=Decimal("1"))
    with pytest.raises(ValidationError) as error:
        duplicate.full_clean()
    assert "code" in error.value.message_dict


def test_lease_creation_marks_unit_occupied(lease, unit):
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_OCCUPIED


def test_lease_ending_vacates_unit(lease, unit):
    lease.end_date = timezone.localdate() - timedelta(days=1)
    lease.save()
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_VACANT


def test_refresh_expires_old_leases_and_frees_units(lease, unit):
    past = timezone.localdate() - timedelta(days=1)
    Lease.objects.filter(pk=lease.pk).update(end_date=past)
    lease.refresh_from_db()
    assert lease.status == Lease.STATUS_ACTIVE

    refresh_lease_statuses()

    lease.refresh_from_db()
    unit.refresh_from_db()
    assert lease.status == Lease.STATUS_EXPIRED
    assert unit.status == Unit.STATUS_VACANT


def test_overlapping_active_lease_is_rejected(tenant, unit, lease):
    today = timezone.localdate()
    other_tenant = Tenant.objects.create(business_name="Salon Bella")
    overlapping = Lease(
        tenant=other_tenant,
        unit=unit,
        start_date=today,
        end_date=today + timedelta(days=30),
        monthly_rent=Decimal("30000"),
        status=Lease.STATUS_ACTIVE,
    )
    with pytest.raises(ValidationError) as error:
        overlapping.full_clean()
    assert "unit" in error.value.message_dict


def test_non_overlapping_lease_is_allowed(tenant, unit, lease):
    far_future = timezone.localdate() + timedelta(days=400)
    other_tenant = Tenant.objects.create(business_name="Salon Bella")
    later = Lease(
        tenant=other_tenant,
        unit=unit,
        start_date=far_future,
        end_date=far_future + timedelta(days=364),
        monthly_rent=Decimal("30000"),
        status=Lease.STATUS_ACTIVE,
    )
    later.full_clean()


def test_draft_lease_does_not_need_overlap_free_dates(tenant, unit, lease):
    today = timezone.localdate()
    other_tenant = Tenant.objects.create(business_name="Salon Bella")
    draft = Lease(
        tenant=other_tenant,
        unit=unit,
        start_date=today,
        end_date=today + timedelta(days=30),
        monthly_rent=Decimal("30000"),
        status=Lease.STATUS_DRAFT,
    )
    draft.full_clean()


def test_escalation_requires_interval_and_next_date(tenant, unit):
    today = timezone.localdate()
    lease = Lease(
        tenant=tenant,
        unit=unit,
        start_date=today,
        end_date=today + timedelta(days=365),
        monthly_rent=Decimal("25000"),
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("5"),
        status=Lease.STATUS_DRAFT,
    )
    with pytest.raises(ValidationError) as error:
        lease.full_clean()
    assert "escalation_interval_months" in error.value.message_dict


def test_percentage_escalation_must_be_sensible(tenant, unit):
    today = timezone.localdate()
    lease = Lease(
        tenant=tenant,
        unit=unit,
        start_date=today,
        end_date=today + timedelta(days=365),
        monthly_rent=Decimal("25000"),
        escalation_type=Lease.ESCALATION_PERCENT,
        escalation_value=Decimal("0"),
        escalation_interval_months=12,
        next_escalation_date=today + timedelta(days=365),
        status=Lease.STATUS_DRAFT,
    )
    with pytest.raises(ValidationError) as error:
        lease.full_clean()
    assert "escalation_value" in error.value.message_dict


def test_lease_form_records_initial_and_manual_rent_history(tenant, unit):
    today = timezone.localdate()
    form = LeaseForm(
        data={
            "tenant": tenant.pk,
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "monthly_rent": "25000.00",
            "deposit_amount": "25000.00",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
        }
    )
    assert form.is_valid(), form.errors
    lease = form.save()
    history = LeaseRentHistory.objects.filter(lease=lease)
    assert history.count() == 1
    assert history.first().reason == LeaseRentHistory.REASON_INITIAL
    assert history.first().new_rent == Decimal("25000.00")

    form = LeaseForm(
        data={
            "tenant": tenant.pk,
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "monthly_rent": "27000.00",
            "deposit_amount": "25000.00",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
        },
        instance=lease,
    )
    assert form.is_valid(), form.errors
    lease = form.save()
    manual = LeaseRentHistory.objects.filter(
        lease=lease, reason=LeaseRentHistory.REASON_MANUAL
    )
    assert manual.count() == 1
    assert manual.first().old_rent == Decimal("25000.00")
    assert manual.first().new_rent == Decimal("27000.00")


def test_only_one_primary_contact(tenant):
    first = TenantContact.objects.create(tenant=tenant, name="First", is_primary=True)
    second = TenantContact.objects.create(tenant=tenant, name="Second", is_primary=True)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_primary is False
    assert second.is_primary is True
    assert tenant.primary_contact == second


def test_lease_sets_tenant_primary_unit(tenant, unit, lease):
    tenant.refresh_from_db()
    assert tenant.primary_unit == unit


def test_reserved_unit_stays_reserved_without_lease(unit):
    unit.status = Unit.STATUS_RESERVED
    unit.save()
    sync_unit_status(unit)
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_RESERVED


def test_refresh_unit_statuses_clears_stale_occupied(unit):
    unit.status = Unit.STATUS_OCCUPIED
    unit.save()
    refresh_unit_statuses()
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_VACANT
