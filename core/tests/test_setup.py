import zipfile
from io import BytesIO

import pytest
from django.urls import reverse

from core.models import Settings, User
from core.recovery import recovery_file, store_recovery_code

pytestmark = pytest.mark.django_db


def test_first_run_redirects_login_to_setup(client):
    response = client.get(reverse("login"))
    assert response.status_code == 302
    assert reverse("setup") in response["Location"]

    response = client.get(reverse("setup"))
    assert response.status_code == 200
    assert b"Set up Rentals Manager" in response.content


def test_setup_creates_owner_and_recovery_code(client, monkeypatch, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    monkeypatch.setattr(
        "core.views.generate_recovery_code", lambda: "TEST-CODE-123"
    )

    response = client.post(
        reverse("setup"),
        {
            "company_name": "Mwangaza Properties",
            "address": "Ngong Road",
            "phone": "+254700000000",
            "email": "office@example.com",
            "kra_pin": "P051234567X",
            "letterhead_text": "Mwangaza Properties",
            "backup_folder": str(tmp_path / "backups"),
            "owner_username": "owner",
            "owner_full_name": "Owner One",
            "password1": "Strong-pass-12345",
            "password2": "Strong-pass-12345",
            "default_palette": "forest",
            "brand_color": "#1D4ED8",
        },
    )
    assert response.status_code == 200
    assert b"TEST-CODE-123" in response.content

    owner = User.objects.get(username="owner")
    assert owner.is_superuser is True
    assert owner.theme_palette == "forest"
    assert owner.check_password("Strong-pass-12345")
    app_settings = Settings.load()
    assert app_settings.company_name == "Mwangaza Properties"
    assert app_settings.backup_folder == str(tmp_path / "backups")
    assert recovery_file().exists()


def test_setup_blocked_when_owner_exists(client, django_user_model):
    django_user_model.objects.create_user(username="owner", password="secret-pass-123")
    response = client.get(reverse("setup"))
    assert response.status_code == 302
    assert reverse("login") in response["Location"]


def test_recovery_code_resets_password(settings, tmp_path, django_user_model):
    settings.DATA_DIR = tmp_path
    user = django_user_model.objects.create_user(
        username="owner", password="old-password-123"
    )
    store_recovery_code("RECOVERY-CODE")

    from core.recovery import reset_owner_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        reset_owner_password("WRONG", "new-password-12345")
    reset_owner_password("RECOVERY-CODE", "new-password-12345")
    user.refresh_from_db()
    assert user.check_password("new-password-12345")


def test_help_page_and_support_bundle(logged_in):
    response = logged_in.get(reverse("help_page"))
    assert response.status_code == 200
    assert b"Help" in response.content

    response = logged_in.get(reverse("support_bundle"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    archive = zipfile.ZipFile(BytesIO(response.content))
    assert "version.txt" in archive.namelist()
    assert not any(name.endswith(".sqlite3") for name in archive.namelist())


def test_open_data_folder(logged_in, monkeypatch):
    opened = {}
    monkeypatch.setattr("core.views.os.startfile", lambda path: opened.setdefault("path", path))
    response = logged_in.post(reverse("open_data_folder"))
    assert response.status_code == 302
    assert opened.get("path")


@pytest.fixture
def logged_in(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="help-owner", password="secret-pass-123"
    )
    client.force_login(user)
    return client

@pytest.mark.django_db
def test_seed_demo_creates_units_and_ledger():
    from django.core.management import call_command
    from billing.models import Invoice
    from operations.models import Expense
    from payments.models import Payment
    from property.models import Lease, Tenant, Unit

    call_command("seed_demo", units=5, months=2, verbosity=0)
    assert Unit.objects.count() == 5
    assert Tenant.objects.count() == 5
    assert Lease.objects.count() == 5
    assert Invoice.objects.count() == 10
    assert Payment.objects.count() > 0
    assert Expense.objects.count() == 4
