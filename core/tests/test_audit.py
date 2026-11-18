import pytest

from core.models import AuditLog, Settings


@pytest.mark.django_db
def test_create_is_audited_and_password_is_hidden(django_user_model):
    django_user_model.objects.create_user(username="manager", password="secret-pass-123")
    entry = AuditLog.objects.filter(action="create", model="core.User").first()
    assert entry is not None
    assert entry.action == "create"
    assert entry.changes["after"]["username"] == "manager"
    assert entry.changes["after"]["password"] == "***"
    assert "secret-pass-123" not in str(entry.changes)


@pytest.mark.django_db
def test_update_records_before_and_after(django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="secret-pass-123")
    user.phone = "+254700000000"
    user.save()

    entry = AuditLog.objects.filter(action="update", model="core.User").latest("id")
    assert entry.changes["before"]["phone"] == ""
    assert entry.changes["after"]["phone"] == "+254700000000"
    assert "phone" in entry.changes["before"]


@pytest.mark.django_db
def test_saving_without_changes_does_not_add_an_entry(django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="secret-pass-123")
    before = AuditLog.objects.count()
    user.save()
    assert AuditLog.objects.count() == before


@pytest.mark.django_db
def test_delete_is_audited(django_user_model):
    user = django_user_model.objects.create_user(username="temporary", password="secret-pass-123")
    username = user.username
    user.delete()
    entry = AuditLog.objects.filter(action="delete", model="core.User").latest("id")
    assert entry.changes["before"]["username"] == username
    assert entry.changes["after"] == {}


@pytest.mark.django_db
def test_settings_changes_are_audited():
    settings = Settings.load()
    settings.company_name = "Mwangaza Properties"
    settings.save()

    entry = AuditLog.objects.filter(action="update", model="core.Settings").latest("id")
    assert entry.changes["before"]["company_name"] == "Rental Manager"
    assert entry.changes["after"]["company_name"] == "Mwangaza Properties"


@pytest.mark.django_db
def test_login_is_audited(client, django_user_model):
    django_user_model.objects.create_user(username="manager", password="secret-pass-123")
    assert client.login(username="manager", password="secret-pass-123")
    assert AuditLog.objects.filter(action="login", model="core.User").exists()
