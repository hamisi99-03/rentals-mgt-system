"""Backup and restore helpers for the SQLite database and uploaded files."""

import shutil
import sqlite3
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings as django_settings
from django.db import connections
from django.utils import timezone

from core.middleware import get_current_user
from core.models import AuditLog, BackupLog, Settings

SQLITE_HEADER = b"SQLite format 3\x00"


def default_backup_folder() -> Path:
    configured = Settings.load().backup_folder.strip()
    if configured:
        return Path(configured)
    return Path(django_settings.DATA_DIR) / "backups"


def _timestamp() -> str:
    return timezone.localtime().strftime("%Y%m%d-%H%M%S")


def _zip_media(destination: Path) -> int:
    media_root = Path(django_settings.MEDIA_ROOT)
    if not media_root.exists():
        return 0
    files = [p for p in media_root.rglob("*") if p.is_file()]
    if not files:
        return 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(media_root))
    return destination.stat().st_size


def _write_audit(action: str, log: BackupLog, details: dict, user=None):
    AuditLog.objects.create(
        user=user or get_current_user(),
        action=action,
        model="core.BackupLog",
        object_id=str(log.pk or ""),
        object_repr=str(log)[:255],
        changes=details,
    )


def perform_backup(destination=None, user=None, reason="manual") -> BackupLog:
    """Copy the live SQLite database and media files to the backup folder.

    Uses SQLite's online backup API so it is safe while the app is running.
    Never raises for a failed backup; the result is recorded in BackupLog.
    """
    folder = Path(destination) if destination else default_backup_folder()
    stamp = _timestamp()
    db_destination = folder / f"rentals-{stamp}.sqlite3"
    media_destination = folder / f"media-{stamp}.zip"

    try:
        folder.mkdir(parents=True, exist_ok=True)
        connection = connections["default"]
        connection.ensure_connection()
        # Never commit an enclosing test transaction; the app itself runs autocommit.
        if not connection.in_atomic_block:
            connection.connection.commit()
        with sqlite3.connect(str(db_destination)) as target:
            connection.connection.backup(target)

        size = db_destination.stat().st_size
        size += _zip_media(media_destination)

        log = BackupLog.objects.create(
            destination_path=str(folder),
            size_bytes=size,
            result="ok",
            message=f"Database copied to {db_destination.name}",
        )
        _write_audit(
            "backup",
            log,
            {"destination": str(folder), "files": [db_destination.name], "reason": reason},
            user=user,
        )
        return log
    except Exception as exc:  # noqa: BLE001 - log and report, never crash the app
        log = BackupLog.objects.create(
            destination_path=str(folder),
            size_bytes=0,
            result="failed",
            message=str(exc),
        )
        return log


def last_successful_backup():
    return BackupLog.objects.filter(result="ok").order_by("-timestamp").first()


def needs_daily_backup() -> bool:
    last = last_successful_backup()
    if last is None:
        return True
    return last.timestamp < timezone.now() - timedelta(hours=24)


def is_sqlite_file(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            header = handle.read(len(SQLITE_HEADER))
    except OSError:
        return False
    return header == SQLITE_HEADER


def verify_backup(path: Path) -> str:
    """Return the SQLite integrity check result for a candidate backup file."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()


def perform_restore(source_path, user=None, media_zip=None, target_db=None) -> BackupLog:
    """Restore the database from a backup file. Takes a safety backup first.

    `target_db` exists so tests can restore to a scratch file without replacing
    the live database while the test runner is connected to it.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Backup file not found: {source}")
    if not is_sqlite_file(source):
        raise ValueError("The selected file is not a SQLite database.")

    integrity = verify_backup(source)
    if integrity != "ok":
        raise ValueError(f"Backup failed its integrity check: {integrity}")

    db_name = str(target_db or django_settings.DATABASES["default"]["NAME"])
    if target_db is None and (":memory:" in db_name or "mode=memory" in db_name):
        raise RuntimeError("Cannot restore over an in-memory database.")

    safety = perform_backup(reason="pre-restore", user=user)

    if target_db is None:
        connections.close_all()
    shutil.copy2(source, db_name)

    if media_zip:
        archive_path = Path(media_zip)
        if archive_path.exists():
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(django_settings.MEDIA_ROOT)

    log = BackupLog.objects.create(
        destination_path=str(source),
        size_bytes=source.stat().st_size,
        result="ok",
        message=f"Database restored from {source.name}",
    )
    _write_audit(
        "restore",
        log,
        {
            "source": str(source),
            "safety_backup": safety.destination_path if safety else "",
        },
        user=user,
    )
    return log


def backup_status():
    """Status for the dashboard warning: missing folder or stale backup."""
    folder = default_backup_folder()
    last = last_successful_backup()
    warnings = []
    if not folder.exists():
        warnings.append(f"Backup folder is missing: {folder}")
    if last is None:
        warnings.append("No successful backup has been made yet.")
    else:
        age = timezone.now() - last.timestamp
        if age > timedelta(days=7):
            warnings.append(
                f"The last successful backup was {age.days} days ago."
            )
    return {
        "folder": folder,
        "last": last,
        "exists": folder.exists(),
        "warnings": warnings,
    }
