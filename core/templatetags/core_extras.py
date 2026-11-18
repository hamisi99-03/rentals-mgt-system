"""Template filters and small helpers used by shared components."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return ""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


@register.filter
def widget_name(field):
    try:
        return field.field.widget.__class__.__name__.lower()
    except AttributeError:
        return ""


@register.filter
def money(value, currency=""):
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    formatted = f"{amount:,.2f}"
    return f"{currency} {formatted}".strip() if currency else formatted


@register.filter
def signed_money(value, currency=""):
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "+" if amount > 0 else ""
    formatted = f"{sign}{amount:,.2f}"
    return f"{currency} {formatted}".strip() if currency else formatted


@register.filter
def percentage(value):
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{amount.normalize():f}%"


STATUS_TONES = {
    "occupied": "ok",
    "vacant": "plain",
    "reserved": "warn",
    "active": "ok",
    "former": "plain",
    "draft": "plain",
    "expired": "warn",
    "terminated": "bad",
    "paid": "ok",
    "partial": "warn",
    "unpaid": "plain",
    "overdue": "bad",
    "issued": "accent",
    "void": "bad",
    "posted": "ok",
    "received": "warn",
    "banked": "ok",
    "bounced": "bad",
    "pending": "warn",
    "completed": "ok",
    "suggested": "accent",
    "confirmed": "ok",
    "unmatched": "warn",
    "ignored": "plain",
}


@register.filter
def status_tone(status):
    return STATUS_TONES.get(status, "plain")


@register.simple_tag
def badge_tone(tone):
    allowed = {"ok", "warn", "bad", "accent", "plain"}
    return f"badge--{tone}" if tone in allowed else ""


@register.filter
def audit_summary(changes):
    if not isinstance(changes, dict) or not changes:
        return "-"
    before = changes.get("before") or {}
    after = changes.get("after") or {}
    if before and after:
        keys = [key for key in after if before.get(key) != after.get(key)] or sorted(after)
        return ", ".join(str(key) for key in keys)
    if after:
        return "created"
    if before:
        return "removed: " + ", ".join(sorted(before))
    return ", ".join(f"{key}={value}" for key, value in changes.items())


@register.filter
def basename(value):
    return str(value).replace("\\", "/").rstrip("/").split("/")[-1]


@register.filter
def filesize(bytes_value):
    try:
        size = float(bytes_value)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GB"
