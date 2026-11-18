import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import AuditLog, BackupLog, Settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(
        username="owner",
        password="secret-pass-123",
        full_name="Owner One",
    )


def test_login_page_renders(client):
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert b"Sign in" in response.content


def test_anonymous_is_redirected_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_login_flow(client, owner):
    response = client.post(
        "/accounts/login/",
        {"username": "owner", "password": "secret-pass-123"},
        follow=True,
    )
    assert response.status_code == 200
    assert b"Dashboard" in response.content
    assert AuditLog.objects.filter(action="login", model="core.User").exists()


def test_dashboard_shell_renders(client, owner):
    client.force_login(owner)
    response = client.get("/")
    assert response.status_code == 200
    for label in (b"Dashboard", b"Needs attention", b"Rent due"):
        assert label in response.content


@pytest.mark.parametrize(
    "path",
    [
        "/units/",
        "/tenants/",
        "/billing/",
        "/payments/",
        "/maintenance/",
        "/expenses/",
        "/reports/",
        "/settings/",
        "/settings/appearance/",
        "/settings/activity/",
        "/settings/backup/",
        "/search/?q=test",
    ],
)
def test_shell_pages_render(client, owner, path):
    client.force_login(owner)
    response = client.get(path)
    assert response.status_code == 200


def test_sidebar_lists_every_section(client, owner):
    client.force_login(owner)
    response = client.get("/")
    html = response.content.decode()
    for label in ("Dashboard", "Units", "Tenants", "Billing", "Payments", "Maintenance", "Expenses", "Reports", "Settings"):
        assert label in html


def test_settings_are_saved_and_audited(client, owner):
    client.force_login(owner)
    response = client.post(
        "/settings/",
        {
            "company_name": "Mwangaza Properties",
            "address": "Ngong Road",
            "phone": "+254700000000",
            "email": "office@example.com",
            "kra_pin": "P051234567X",
            "letterhead_text": "Mwangaza Properties Ltd",
            "currency": "KES",
            "vat_rate": "16.00",
            "withholding_rate": "10.00",
            "invoice_prefix": "INV",
            "receipt_prefix": "RCT",
            "number_separator": "-",
            "number_padding": "4",
            "invoice_due_day": "5",
            "renewal_alert_days": "60",
            "backup_folder": "",
            "reminder_template": "Hello {tenant}",
            "default_palette": "ocean",
            "brand_color": "",
            "auto_lock_minutes": "20",
        },
    )
    assert response.status_code == 302
    assert Settings.load().company_name == "Mwangaza Properties"
    owner.refresh_from_db()
    assert owner.auto_lock_minutes == 20
    assert AuditLog.objects.filter(action="update", model="core.Settings").exists()


def test_settings_reject_invalid_vat_rate(client, owner):
    client.force_login(owner)
    response = client.post(
        "/settings/",
        {
            "company_name": "Rental Manager",
            "currency": "KES",
            "vat_rate": "150",
            "withholding_rate": "10",
            "invoice_prefix": "INV",
            "receipt_prefix": "RCT",
            "number_separator": "-",
            "number_padding": "4",
            "invoice_due_day": "5",
            "renewal_alert_days": "60",
            "reminder_template": "Hello",
            "default_palette": "ocean",
            "auto_lock_minutes": "15",
        },
    )
    assert response.status_code == 200
    assert Settings.load().vat_rate != 150


def test_appearance_form_saves_theme(client, owner):
    client.force_login(owner)
    response = client.post(
        "/settings/appearance/",
        {
            "theme_mode": "dark",
            "theme_palette": "forest",
            "theme_density": "compact",
            "theme_text_size": "large",
        },
    )
    assert response.status_code == 302
    owner.refresh_from_db()
    assert owner.theme_mode == "dark"
    assert owner.theme_palette == "forest"
    assert owner.theme_density == "compact"
    assert owner.theme_text_size == "large"
    assert AuditLog.objects.filter(action="update", model="core.User").exists()


def test_appearance_json_endpoint_saves_theme(client, owner):
    client.force_login(owner)
    response = client.post(
        "/settings/appearance/theme/",
        data=json.dumps(
            {"mode": "light", "palette": "plum", "density": "comfortable", "textSize": "small"}
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    owner.refresh_from_db()
    assert owner.theme_palette == "plum"
    assert owner.theme_text_size == "small"


def test_appearance_json_endpoint_validates(client, owner):
    client.force_login(owner)
    response = client.post(
        "/settings/appearance/theme/",
        data=json.dumps({"mode": "neon", "palette": "ocean"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_activity_log_lists_entries(client, owner):
    client.force_login(owner)
    response = client.get("/settings/activity/")
    assert response.status_code == 200
    assert b"core.User" in response.content
    assert b"Login" in response.content or b"Create" in response.content


@pytest.mark.django_db(transaction=True)
def test_manual_backup_view(client, owner, tmp_path):
    client.force_login(owner)
    settings = Settings.load()
    settings.backup_folder = str(tmp_path)
    settings.save()

    response = client.post("/settings/backup/now/")
    assert response.status_code == 302
    assert BackupLog.objects.filter(result="ok").exists()
    assert list(tmp_path.glob("rentals-*.sqlite3"))
    assert AuditLog.objects.filter(action="backup").exists()


def test_logout_requires_post_and_redirects(client, owner):
    client.force_login(owner)
    assert client.get("/accounts/logout/").status_code == 405
    response = client.post("/accounts/logout/")
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/"

def test_lock_endpoint_logs_out(client, owner):
    client.force_login(owner)
    response = client.post("/accounts/lock/")
    assert response.status_code == 204
    assert client.get("/").status_code == 302


def test_idle_middleware_locks_an_old_session(client, owner):
    client.force_login(owner)
    session = client.session
    session["last_activity"] = (
        timezone.now() - timedelta(minutes=owner.auto_lock_minutes + 1)
    ).isoformat()
    session.save()

    response = client.get("/")
    assert response.status_code == 302
    assert "locked=1" in response["Location"]
