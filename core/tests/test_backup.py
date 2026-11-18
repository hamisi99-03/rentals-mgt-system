from pathlib import Path

import pytest
from django.conf import settings as django_settings

from core.backup import (
    default_backup_folder,
    is_sqlite_file,
    needs_daily_backup,
    perform_backup,
    perform_restore,
)
from core.models import AuditLog, BackupLog, Settings


@pytest.mark.django_db(transaction=True)
def test_backup_writes_database_and_log(tmp_path):
    log = perform_backup(destination=tmp_path, reason="test")

    assert log.result == "ok"
    files = list(tmp_path.glob("rentals-*.sqlite3"))
    assert len(files) == 1
    assert is_sqlite_file(files[0])
    assert log.size_bytes > 0
    assert BackupLog.objects.filter(pk=log.pk, result="ok").exists()
    assert AuditLog.objects.filter(action="backup").exists()


@pytest.mark.django_db
def test_failed_backup_is_logged(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")

    log = perform_backup(destination=blocker)

    assert log.result == "failed"
    assert log.message


@pytest.mark.django_db(transaction=True)
def test_needs_daily_backup_flips_after_success(tmp_path):
    assert needs_daily_backup() is True
    perform_backup(destination=tmp_path)
    assert needs_daily_backup() is False


@pytest.mark.django_db
def test_restore_rejects_non_sqlite_file(tmp_path):
    bad = tmp_path / "fake.sqlite3"
    bad.write_text("not a database", encoding="utf-8")
    with pytest.raises(ValueError):
        perform_restore(bad)


@pytest.mark.django_db(transaction=True)
def test_backup_then_restore_round_trip(tmp_path, django_user_model):
    django_user_model.objects.create_user(username="before-backup", password="secret-pass-123")
    log = perform_backup(destination=tmp_path, reason="test")
    assert log.result == "ok"

    django_user_model.objects.create_user(username="after-backup", password="secret-pass-123")
    assert django_user_model.objects.filter(username="after-backup").exists()

    backup_file = next(tmp_path.glob("rentals-*.sqlite3"))
    restored = tmp_path / "restored.sqlite3"
    perform_restore(backup_file, target_db=restored)

    import sqlite3

    connection = sqlite3.connect(restored)
    try:
        usernames = {
            row[0] for row in connection.execute("SELECT username FROM core_user")
        }
    finally:
        connection.close()

    assert "before-backup" in usernames
    assert "after-backup" not in usernames
    assert AuditLog.objects.filter(action="restore").exists()


@pytest.mark.django_db
def test_backup_folder_defaults_and_override(tmp_path):
    settings = Settings.load()
    settings.backup_folder = ""
    settings.save()
    assert default_backup_folder() == Path(django_settings.BASE_DIR) / "backups"

    settings.backup_folder = str(tmp_path)
    settings.save()
    assert default_backup_folder() == tmp_path
