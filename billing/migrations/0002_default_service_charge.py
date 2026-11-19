from decimal import Decimal

from django.db import migrations

SERVICE_CHARGE_NAME = "Service charge (water, electricity, security, toilet)"


def add_default_service_charge(apps, schema_editor):
    ChargeType = apps.get_model("billing", "ChargeType")
    LeaseCharge = apps.get_model("billing", "LeaseCharge")
    Lease = apps.get_model("property", "Lease")
    Settings = apps.get_model("core", "Settings")

    amount = (
        Settings.objects.filter(pk=1)
        .values_list("service_charge_amount", flat=True)
        .first()
    )
    amount = amount if amount is not None else Decimal("500.00")

    charge_type, _created = ChargeType.objects.get_or_create(
        name=SERVICE_CHARGE_NAME,
        defaults={
            "kind": "service",
            "vat_applicable": False,
            "is_active": True,
        },
    )

    leases = Lease.objects.filter(status__in=["active", "expired"])
    for lease in leases.iterator():
        LeaseCharge.objects.get_or_create(
            lease_id=lease.pk,
            charge_type_id=charge_type.pk,
            defaults={
                "amount": amount,
                "frequency": "monthly",
                "start_date": lease.start_date,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
        ("property", "0001_initial"),
        ("core", "0004_settings_service_charge_amount"),
    ]

    operations = [
        migrations.RunPython(add_default_service_charge, migrations.RunPython.noop),
    ]
