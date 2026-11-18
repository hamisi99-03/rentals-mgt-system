from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from core.models import AuditLog, Settings, User


@pytest.mark.django_db
def test_user_defaults(django_user_model):
    user = django_user_model.objects.create_user(username="owner", password="secret-pass-123")
    assert user.auto_lock_minutes == 15
    assert user.theme_mode == User.MODE_SYSTEM
    assert user.theme_palette == "ocean"
    assert user.theme_density == "comfortable"
    assert user.theme_text_size == "medium"
    assert user.display_name == "owner"


@pytest.mark.django_db
def test_user_display_name_prefers_full_name(django_user_model):
    user = django_user_model.objects.create_user(
        username="owner", password="secret-pass-123", full_name="Amina Owner"
    )
    assert user.display_name == "Amina Owner"


@pytest.mark.django_db
def test_settings_is_a_singleton():
    first = Settings.load()
    second = Settings.load()
    assert first.pk == 1
    assert second.pk == 1
    assert Settings.objects.count() == 1
    assert first.company_name == "Rental Manager"
    assert first.currency == "KES"


@pytest.mark.django_db
def test_settings_money_defaults_are_decimal():
    settings = Settings.load()
    assert settings.vat_enabled is False
    assert settings.vat_rate == Decimal("16.00")
    assert settings.withholding_rate == Decimal("10.00")
    assert settings.invoice_prefix == "INV"
    assert settings.receipt_prefix == "RCT"
    assert settings.number_padding == 4
    assert settings.invoice_due_day == 5
    assert settings.renewal_alert_days == 60
    assert settings.default_palette == "ocean"


@pytest.mark.django_db
def test_settings_cannot_be_deleted():
    settings = Settings.load()
    with pytest.raises(ValidationError):
        settings.delete()


@pytest.mark.django_db
def test_brand_colour_validation():
    settings = Settings.load()
    settings.brand_color = "blue"
    with pytest.raises(ValidationError):
        settings.full_clean()

    settings.brand_color = "#1D4ED8"
    settings.full_clean()


@pytest.mark.django_db
def test_percentage_settings_validation():
    settings = Settings.load()
    settings.vat_rate = Decimal("150.00")
    settings.withholding_rate = Decimal("-1.00")
    with pytest.raises(ValidationError) as error:
        settings.full_clean()
    assert "vat_rate" in error.value.message_dict
    assert "withholding_rate" in error.value.message_dict


@pytest.mark.django_db
def test_audit_log_is_append_only(django_user_model):
    django_user_model.objects.create_user(username="manager", password="secret-pass-123")
    entry = AuditLog.objects.filter(action="create", model="core.User").first()
    assert entry is not None
    entry.action = "delete"
    with pytest.raises(ValidationError):
        entry.save()
    with pytest.raises(ValidationError):
        entry.delete()
