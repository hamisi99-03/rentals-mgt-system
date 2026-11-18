from datetime import date
from decimal import Decimal

import pytest

from billing.models import ChargeType, LeaseCharge, MeterReading, UtilityType
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
    settings.vat_rate = Decimal("16.00")
    settings.invoice_prefix = "INV"
    settings.receipt_prefix = "RCT"
    settings.number_separator = "-"
    settings.number_padding = 4
    settings.invoice_due_day = 5
    settings.brand_color = ""
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
    return Lease.objects.create(
        tenant=tenant,
        unit=unit,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        monthly_rent=Decimal("1000.00"),
        deposit_amount=Decimal("2000.00"),
        status=Lease.STATUS_ACTIVE,
    )


@pytest.fixture
def make_unit(building, floor):
    counter = {"n": 1}

    def _make(code=None):
        counter["n"] += 1
        return Unit.objects.create(
            building=building,
            floor=floor,
            code=code or f"B{counter['n']:02d}",
            size_sqm=Decimal("20.00"),
            base_rent=Decimal("1000.00"),
        )

    return _make


@pytest.fixture
def make_lease(tenant, make_unit):
    def _make(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        rent="1000.00",
        status=Lease.STATUS_ACTIVE,
        unit=None,
        **kwargs,
    ):
        return Lease.objects.create(
            tenant=tenant,
            unit=unit or make_unit(),
            start_date=start_date,
            end_date=end_date,
            monthly_rent=Decimal(rent),
            deposit_amount=Decimal("2000.00"),
            status=status,
            **kwargs,
        )

    return _make


@pytest.fixture
def service_type():
    return ChargeType.objects.create(name="Garbage", kind=ChargeType.KIND_SERVICE)


@pytest.fixture
def utility_type():
    return UtilityType.objects.create(
        name="Water", measure="m3", rate_per_unit=Decimal("50.00")
    )


def add_charge(lease, charge_type, amount="300.00", frequency=LeaseCharge.FREQUENCY_MONTHLY, start=date(2026, 1, 1), end=None):
    return LeaseCharge.objects.create(
        lease=lease,
        charge_type=charge_type,
        amount=Decimal(amount),
        frequency=frequency,
        start_date=start,
        end_date=end,
    )


def add_reading(unit, utility_type, reading_date, value):
    return MeterReading.objects.create(
        unit=unit,
        utility_type=utility_type,
        reading_date=reading_date,
        reading_value=Decimal(str(value)),
    )
