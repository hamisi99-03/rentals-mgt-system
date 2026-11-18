"""Seed a realistic demo dataset: units, tenants, 12 months of billing and payments."""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, transaction
from django.utils import timezone

from billing.models import UtilityType
from billing.services import add_months, default_due_date, generate_invoice
from core.models import Settings
from operations.models import (
    Deposit,
    Expense,
    ExpenseCategory,
    MaintenanceRequest,
    Prospect,
)
from payments.services import record_payment
from property.models import Building, Floor, Lease, Tenant, TenantContact, Unit


class Command(BaseCommand):
    help = "Create 40 units, tenants, leases and 12 months of invoices/payments for demos."

    def add_arguments(self, parser):
        parser.add_argument("--units", type=int, default=40)
        parser.add_argument("--months", type=int, default=12)

    def handle(self, *args, **options):
        units_target = max(1, min(options["units"], 100))
        months = max(1, min(options["months"], 24))

        try:
            has_data = Unit.objects.exists() or Tenant.objects.exists()
        except OperationalError as exc:
            raise CommandError(
                "Database tables are missing. Run 'python manage.py migrate' "
                "before seeding, or start the desktop app once so it migrates."
            ) from exc
        if has_data:
            raise CommandError(
                "The database already has units or tenants. Use a fresh data folder to seed."
            )

        today = timezone.localdate()
        current_start = today.replace(day=1)
        settings_obj = Settings.load()
        currency = settings_obj.currency

        created = {
            "units": 0,
            "tenants": 0,
            "leases": 0,
            "invoices": 0,
            "payments": 0,
            "expenses": 0,
        }

        with transaction.atomic():
            buildings = [
                Building.objects.create(name="Mwangaza Plaza", address="Ngong Road"),
                Building.objects.create(name="Riverside Court", address="Riverside Drive"),
            ]
            floors = []
            for building in buildings:
                floors.append(
                    Floor.objects.create(building=building, name="Ground floor", sort_order=0)
                )
                floors.append(
                    Floor.objects.create(building=building, name="First floor", sort_order=1)
                )

            UtilityType.objects.create(name="Water", measure="m3", rate_per_unit=Decimal("50.00"))
            UtilityType.objects.create(
                name="Electricity", measure="kWh", rate_per_unit=Decimal("25.00")
            )

            leases = []
            for index in range(1, units_target + 1):
                building_index = (index - 1) // 20 % len(buildings)
                building = buildings[building_index]
                floor = floors[building_index * 2 + (index - 1) % 2]
                code = f"A{index:02d}" if index <= 20 else f"B{index - 20:02d}"
                unit = Unit.objects.create(
                    building=building,
                    floor=floor,
                    code=code,
                    size_sqm=Decimal("20.00") + Decimal(index % 10),
                    base_rent=Decimal("15000.00") + Decimal((index % 6) * 2500),
                    notes="Demo unit",
                )
                tenant = Tenant.objects.create(
                    business_name=f"Demo Tenant {index:02d}",
                    trade=["Retail", "Salon", "Cafe", "Services"][index % 4],
                    vat_applicable=index % 5 == 0,
                    withholding_applicable=index % 7 == 0,
                )
                TenantContact.objects.create(
                    tenant=tenant,
                    name=f"Contact {index:02d}",
                    role_title="Owner",
                    phone=f"+2547000{index:05d}",
                    is_primary=True,
                )
                lease = Lease.objects.create(
                    tenant=tenant,
                    unit=unit,
                    start_date=add_months(current_start, -(months + 1)),
                    end_date=add_months(current_start, 12),
                    monthly_rent=unit.base_rent,
                    deposit_amount=unit.base_rent * 2,
                    status=Lease.STATUS_ACTIVE,
                )
                Deposit.objects.create(
                    lease=lease,
                    amount_received=lease.deposit_amount,
                    received_date=lease.start_date,
                )
                leases.append(lease)

            for month_offset in range(months - 1, -1, -1):
                period_start = add_months(current_start, -month_offset)
                first_invoice = generate_invoice
                due_date = default_due_date(period_start, settings_obj)
                for lease_index, lease in enumerate(leases):
                    invoice, made = first_invoice(
                        lease,
                        period_start,
                        add_months(period_start, 1) - timedelta(days=1),
                        due_date,
                        settings_obj=settings_obj,
                    )
                    if not made:
                        continue
                    created["invoices"] += 1
                    payment_cycle = (lease_index + month_offset) % 6
                    if payment_cycle in (0, 3, 4):
                        cash = invoice.total
                    elif payment_cycle == 1:
                        cash = (invoice.total * Decimal("0.5")).quantize(Decimal("0.01"))
                    else:
                        continue
                    if cash <= 0:
                        continue
                    received = min(today, max(invoice.issue_date, due_date))
                    withholding = Decimal("0.00")
                    if payment_cycle == 3 and lease.tenant.withholding_applicable:
                        withholding = (cash * Decimal("0.10")).quantize(Decimal("0.01"))
                        cash = cash - withholding
                    record_payment(
                        lease.tenant,
                        received,
                        ["mpesa", "bank", "cash"][lease_index % 3],
                        cash,
                        withholding_amount=withholding,
                        reference=f"DEMO{month_offset:02d}{lease_index:02d}",
                    )
                    created["payments"] += 1

            categories = [
                ExpenseCategory.objects.create(name="Utilities"),
                ExpenseCategory.objects.create(name="Repairs"),
                ExpenseCategory.objects.create(name="Security"),
            ]
            for month_offset in range(months):
                month = add_months(current_start, -month_offset)
                for index in range(2):
                    Expense.objects.create(
                        category=categories[(month_offset + index) % len(categories)],
                        expense_date=month + timedelta(days=5 + index * 10),
                        amount=Decimal("2500.00") + Decimal(index * 1500),
                        payee=["KPLC", "Fundi John", "Guard Services"][index % 3],
                        description="Demo monthly expense",
                        payment_method="mpesa",
                    )
                    created["expenses"] += 1

            for index in range(4):
                MaintenanceRequest.objects.create(
                    unit=leases[index].unit,
                    tenant=leases[index].tenant,
                    title=f"Demo repair {index + 1}",
                    priority=["low", "normal", "urgent"][index % 3],
                    status=["open", "in_progress", "done"][index % 3],
                    reported_date=today - timedelta(days=index * 3),
                    cost=Decimal("500.00") * (index + 1),
                )

            for index in range(3):
                Prospect.objects.create(
                    name=f"Prospect {index + 1}",
                    business=f"Prospect Business {index + 1}",
                    phone=f"+2547111{index:05d}",
                    interested_unit=leases[index].unit,
                    status=Prospect.STATUS_VIEWING,
                    follow_up_date=today + timedelta(days=index + 1),
                )

            created["units"] = Unit.objects.count()
            created["tenants"] = Tenant.objects.count()
            created["leases"] = Lease.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo data: "
                + ", ".join(f"{key}={value}" for key, value in created.items())
                + f" ({currency})."
            )
        )
