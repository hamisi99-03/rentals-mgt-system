from decimal import Decimal

import pytest
from django.utils import timezone

from property.models import Building, Floor, Unit


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(
        username="owner", password="secret-pass-123", full_name="Owner One"
    )


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def building():
    return Building.objects.create(name="Mwangaza Plaza", address="Ngong Road")


@pytest.fixture
def floor(building):
    return Floor.objects.create(building=building, name="Ground floor", sort_order=0)


@pytest.fixture
def unit(building, floor):
    return Unit.objects.create(
        building=building,
        floor=floor,
        code="A01",
        size_sqm=Decimal("24.00"),
        base_rent=Decimal("25000.00"),
    )


@pytest.fixture
def tenant():
    from property.models import Tenant

    return Tenant.objects.create(business_name="Mama Mboga Ltd", trade="Grocery")


@pytest.fixture
def lease(tenant, unit):
    from property.models import Lease

    today = timezone.localdate()
    return Lease.objects.create(
        tenant=tenant,
        unit=unit,
        start_date=today.replace(day=1),
        end_date=today.replace(month=12, day=31),
        monthly_rent=Decimal("25000.00"),
        deposit_amount=Decimal("25000.00"),
        status=Lease.STATUS_ACTIVE,
    )
