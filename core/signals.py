"""Audit trail signals: every business model change writes an AuditLog row."""

from django.contrib.auth.signals import user_logged_in
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.middleware import get_current_user
from core.models import AuditLog, BackupLog

AUDITED_APPS = {"core", "property", "billing", "payments", "operations", "reports"}
EXCLUDED_MODELS = {"AuditLog", "BackupLog", "Session", "LogEntry", "Permission", "Group"}
SENSITIVE_FIELDS = {"password"}
IGNORED_CHANGE_FIELDS = {"last_login", "updated_at"}


def _is_audited(sender) -> bool:
    return (
        sender._meta.app_label in AUDITED_APPS
        and sender.__name__ not in EXCLUDED_MODELS
        and not sender._meta.abstract
    )


def _jsonable(value):
    from decimal import Decimal
    from uuid import UUID

    from django.db.models.fields.files import FieldFile

    if isinstance(value, FieldFile):
        return value.name or ""
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _snapshot(instance) -> dict:
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in SENSITIVE_FIELDS:
            data[field.name] = "***" if getattr(instance, field.attname) else ""
            continue
        value = getattr(instance, field.attname, None)
        data[field.name] = _jsonable(value)
    # Round-trip through the Django encoder so the JSONField always receives plain types.
    import json

    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


@receiver(pre_save)
def _capture_before(sender, instance, **kwargs):  # noqa: ANN001
    if not _is_audited(sender) or not instance.pk:
        instance.__audit_before = None
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance.__audit_before = None
        return
    instance.__audit_before = _snapshot(old)


@receiver(post_save)
def _audit_save(sender, instance, created, **kwargs):  # noqa: ANN001
    if not _is_audited(sender):
        return

    before = getattr(instance, "__audit_before", None)
    after = _snapshot(instance)

    if created:
        changes = {"before": {}, "after": after}
        action = "create"
    else:
        changed = {
            key
            for key in set(before or {}) | set(after)
            if (before or {}).get(key) != after.get(key)
        }
        if not changed or changed <= IGNORED_CHANGE_FIELDS:
            return
        changes = {
            "before": {k: (before or {}).get(k) for k in changed},
            "after": {k: after.get(k) for k in changed},
        }
        action = "update"

    user = get_current_user()
    if user is None and getattr(instance, "created_by_id", None):
        user = instance.created_by

    AuditLog.objects.create(
        user=user,
        action=action,
        model=f"{sender._meta.app_label}.{sender.__name__}",
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
    )


@receiver(post_delete)
def _audit_delete(sender, instance, **kwargs):  # noqa: ANN001
    if not _is_audited(sender):
        return
    user = get_current_user()
    if user is None and getattr(instance, "created_by_id", None):
        user = instance.created_by
    AuditLog.objects.create(
        user=user,
        action="delete",
        model=f"{sender._meta.app_label}.{sender.__name__}",
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes={"before": _snapshot(instance), "after": {}},
    )


@receiver(user_logged_in)
def _audit_login(sender, request, user, **kwargs):  # noqa: ANN001
    AuditLog.objects.create(
        user=user,
        action="login",
        model="core.User",
        object_id=str(user.pk),
        object_repr=str(user)[:255],
        changes={},
    )
