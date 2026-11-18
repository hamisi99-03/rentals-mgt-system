from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.services import add_months, generate_invoice
from core.models import Settings
from property.models import Building, Floor, Lease, Tenant, Unit


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
def settings_obj():
    settings = Settings.load()
    settings.vat_enabled = False
    settings.invoice_prefix = "INV"
    settings.receipt_prefix = "RCT"
    settings.number_separator = "-"
    settings.number_padding = 4
    settings.save()
    return settings


@pytest.fixture
def building():
    return Building.objects.create(name="Mwangaza Plaza")


@pytest.fixture
def floor(building):
    return Floor.objects.create(building=building, name="Ground floor")


@pytest.fixture
def unit(building, floor):
    return Unit.objects.create(
        building=building,
        floor=floor,
        code="A01",
        size_sqm=Decimal("20.00"),
        base_rent=Decimal("1000.00"),
    )


@pytest.fixture
def tenant():
    return Tenant.objects.create(business_name="Mama Mboga Ltd", trade="Grocery")


@pytest.fixture
def lease(tenant, unit):
    today = timezone.localdate()
    return Lease.objects.create(
        tenant=tenant,
        unit=unit,
        start_date=add_months(today.replace(day=1), -12),
        end_date=add_months(today.replace(day=1), 12),
        monthly_rent=Decimal("1000.00"),
        deposit_amount=Decimal("2000.00"),
        status=Lease.STATUS_ACTIVE,
    )


@pytest.fixture
def invoice(lease):
    today = timezone.localdate()
    start = today.replace(day=1)
    end = add_months(start, 1) - timedelta(days=1)
    invoice, _ = generate_invoice(
        lease, start, end, today + timedelta(days=10)
    )
    return invoice
