from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from property.models import (
    Building,
    Document,
    Floor,
    Lease,
    Tenant,
    TenantContact,
    Unit,
)

pytestmark = pytest.mark.django_db


def test_unit_pages_require_login(client):
    for name in ("units", "tenants", "leases"):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


def test_units_table_and_grid_views(logged_in, unit, tenant, lease):
    response = logged_in.get(reverse("units"))
    assert response.status_code == 200
    assert b"A01" in response.content
    assert b"Mama Mboga Ltd" in response.content

    response = logged_in.get(reverse("units") + "?view=grid")
    assert response.status_code == 200
    assert b"unit-tile" in response.content
    assert b"A01" in response.content


def test_units_filters(logged_in, unit, tenant, lease):
    response = logged_in.get(reverse("units") + "?q=Mama")
    assert b"A01" in response.content
    response = logged_in.get(reverse("units") + "?q=NothingMatches")
    assert b"A01" not in response.content
    response = logged_in.get(reverse("units") + "?status=reserved")
    assert b"A01" not in response.content


def test_create_building_floor_and_unit(logged_in):
    response = logged_in.post(
        reverse("buildings"),
        {"name": "Mwangaza Plaza", "address": "Ngong Road", "notes": ""},
    )
    assert response.status_code == 302
    building = Building.objects.get(name="Mwangaza Plaza")

    response = logged_in.post(
        reverse("building_detail", kwargs={"pk": building.pk}),
        {"building": building.pk, "name": "Ground floor", "sort_order": "1"},
    )
    assert response.status_code == 302
    floor = Floor.objects.get(building=building, name="Ground floor")

    response = logged_in.post(
        reverse("unit_create"),
        {
            "building": building.pk,
            "floor": floor.pk,
            "code": "a12",
            "size_sqm": "24.50",
            "base_rent": "25000.00",
            "status": "vacant",
            "is_active": "on",
            "notes": "",
        },
    )
    assert response.status_code == 302
    unit = Unit.objects.get(code="a12")
    assert unit.status == Unit.STATUS_VACANT
    assert unit.size_sqm == Decimal("24.50")


def test_unit_detail_and_edit(logged_in, unit):
    response = logged_in.get(reverse("unit_detail", kwargs={"pk": unit.pk}))
    assert response.status_code == 200
    assert b"A01" in response.content

    response = logged_in.post(
        reverse("unit_edit", kwargs={"pk": unit.pk}),
        {
            "building": unit.building_id,
            "floor": unit.floor_id,
            "code": unit.code,
            "size_sqm": "30.00",
            "base_rent": "30000.00",
            "status": "reserved",
            "is_active": "on",
            "notes": "Corner unit",
        },
    )
    assert response.status_code == 302
    unit.refresh_from_db()
    assert unit.base_rent == Decimal("30000.00")
    assert unit.status == Unit.STATUS_RESERVED
    assert unit.notes == "Corner unit"


def test_unit_archive_blocked_with_active_lease(logged_in, unit, lease):
    response = logged_in.post(reverse("unit_toggle_active", kwargs={"pk": unit.pk}))
    assert response.status_code == 302
    unit.refresh_from_db()
    assert unit.is_active is True


def test_unit_archive_and_restore(logged_in, unit):
    logged_in.post(reverse("unit_toggle_active", kwargs={"pk": unit.pk}))
    unit.refresh_from_db()
    assert unit.is_active is False

    logged_in.post(reverse("unit_toggle_active", kwargs={"pk": unit.pk}))
    unit.refresh_from_db()
    assert unit.is_active is True


def test_building_delete_is_guarded(logged_in, building, floor, unit):
    response = logged_in.post(reverse("building_delete", kwargs={"pk": building.pk}))
    assert response.status_code == 302
    assert Building.objects.filter(pk=building.pk).exists()


def test_building_and_floor_delete_when_empty(logged_in):
    building = Building.objects.create(name="Empty")
    floor = Floor.objects.create(building=building, name="Ground")
    logged_in.post(reverse("floor_delete", kwargs={"pk": floor.pk}))
    assert not Floor.objects.filter(pk=floor.pk).exists()
    logged_in.post(reverse("building_delete", kwargs={"pk": building.pk}))
    assert not Building.objects.filter(pk=building.pk).exists()


def test_tenant_create_and_all_profile_tabs(logged_in):
    response = logged_in.post(
        reverse("tenant_create"),
        {
            "business_name": "Salon Bella",
            "trade": "Beauty",
            "id_or_kra_pin": "12345",
            "permit_number": "P-1",
            "primary_unit": "",
            "status": "active",
            "notes": "Corner shop",
        },
    )
    assert response.status_code == 302
    tenant = Tenant.objects.get(business_name="Salon Bella")
    assert logged_in.get(reverse("tenant_edit", kwargs={"pk": tenant.pk})).status_code == 200
    for tab in ("overview", "lease", "statement", "payments", "documents", "notes"):
        response = logged_in.get(
            reverse("tenant_detail", kwargs={"pk": tenant.pk}) + f"?tab={tab}"
        )
        assert response.status_code == 200


def test_tenant_contact_lifecycle(logged_in, tenant):
    response = logged_in.post(
        reverse("contact_create", kwargs={"pk": tenant.pk}),
        {
            "name": "Asha",
            "role_title": "Owner",
            "phone": "+254700000001",
            "email": "asha@example.com",
            "is_primary": "on",
        },
    )
    assert response.status_code == 302
    contact = TenantContact.objects.get(tenant=tenant, name="Asha")
    assert contact.is_primary is True
    assert logged_in.get(reverse("contact_edit", kwargs={"pk": contact.pk})).status_code == 200

    response = logged_in.post(
        reverse("contact_edit", kwargs={"pk": contact.pk}),
        {
            "name": "Asha M.",
            "role_title": "Owner",
            "phone": "+254700000002",
            "email": "asha@example.com",
            "is_primary": "on",
        },
    )
    assert response.status_code == 302
    contact.refresh_from_db()
    assert contact.name == "Asha M."

    logged_in.post(reverse("contact_delete", kwargs={"pk": contact.pk}))
    assert not TenantContact.objects.filter(pk=contact.pk).exists()


def test_document_upload_and_delete(logged_in, tenant):
    upload = SimpleUploadedFile(
        "permit.pdf", b"%PDF-1.4 test", content_type="application/pdf"
    )
    response = logged_in.post(
        reverse("document_upload"),
        {
            "owner_type": "tenant",
            "owner_id": tenant.pk,
            "doc_type": "permit",
            "file": upload,
        },
    )
    assert response.status_code == 302
    document = Document.objects.get(owner_id=tenant.pk)
    assert document.get_doc_type_display() == "Permit"
    assert document.uploaded_by is not None

    logged_in.post(reverse("document_delete", kwargs={"pk": document.pk}))
    assert not Document.objects.filter(pk=document.pk).exists()


def test_tenant_archive_blocked_with_active_lease(logged_in, tenant, lease):
    logged_in.post(reverse("tenant_toggle_status", kwargs={"pk": tenant.pk}))
    tenant.refresh_from_db()
    assert tenant.status == Tenant.STATUS_ACTIVE


def test_tenant_archive_without_lease(logged_in, tenant):
    logged_in.post(reverse("tenant_toggle_status", kwargs={"pk": tenant.pk}))
    tenant.refresh_from_db()
    assert tenant.status == Tenant.STATUS_FORMER
    logged_in.post(reverse("tenant_toggle_status", kwargs={"pk": tenant.pk}))
    tenant.refresh_from_db()
    assert tenant.status == Tenant.STATUS_ACTIVE


def test_create_lease_occupies_unit(logged_in, tenant, unit):
    today = timezone.localdate()
    response = logged_in.post(
        reverse("lease_create"),
        {
            "tenant": tenant.pk,
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "monthly_rent": "25000.00",
            "deposit_amount": "25000.00",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
            "notes": "",
        },
    )
    assert response.status_code == 302
    lease = Lease.objects.get(tenant=tenant, unit=unit)
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_OCCUPIED
    assert lease.rent_history.count() == 1

    response = logged_in.get(reverse("lease_detail", kwargs={"pk": lease.pk}))
    assert response.status_code == 200


def test_overlapping_lease_rejected_by_form(logged_in, tenant, unit, lease):
    today = timezone.localdate()
    other = Tenant.objects.create(business_name="Salon Bella")
    response = logged_in.post(
        reverse("lease_create"),
        {
            "tenant": other.pk,
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
            "monthly_rent": "30000.00",
            "deposit_amount": "0",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
        },
    )
    assert response.status_code == 200
    assert Lease.objects.count() == 1
    assert b"already has an active lease" in response.content


def test_terminate_lease_frees_unit(logged_in, lease, unit):
    response = logged_in.post(
        reverse("lease_terminate", kwargs={"pk": lease.pk}),
        {"terminated_on": timezone.localdate().isoformat(), "termination_reason": "Moved out"},
    )
    assert response.status_code == 302
    lease.refresh_from_db()
    unit.refresh_from_db()
    assert lease.status == Lease.STATUS_TERMINATED
    assert lease.termination_reason == "Moved out"
    assert unit.status == Unit.STATUS_VACANT


def test_leases_list_and_filters(logged_in, lease):
    response = logged_in.get(reverse("leases"))
    assert response.status_code == 200
    assert lease.unit.code.encode() in response.content

    response = logged_in.get(reverse("leases") + "?q=Unknown")
    assert lease.unit.code.encode() not in response.content


def test_building_management_pages_render(logged_in, building, floor, unit):
    for url in (
        reverse("buildings"),
        reverse("building_detail", kwargs={"pk": building.pk}),
        reverse("building_edit", kwargs={"pk": building.pk}),
        reverse("floor_edit", kwargs={"pk": floor.pk}),
        reverse("unit_create"),
        reverse("unit_edit", kwargs={"pk": unit.pk}),
        reverse("tenant_create"),
        reverse("lease_create"),
        reverse("import_data"),
    ):
        assert logged_in.get(url).status_code == 200
