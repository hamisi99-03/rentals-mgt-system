"""Template context shared by every screen."""

from core.models import Settings, User

NAV_ITEMS = [
    {"key": "dashboard", "label": "Dashboard", "url_name": "dashboard", "icon": "dashboard"},
    {"key": "units", "label": "Units", "url_name": "units", "icon": "units"},
    {"key": "tenants", "label": "Tenants", "url_name": "tenants", "icon": "tenants"},
    {"key": "billing", "label": "Billing", "url_name": "billing", "icon": "billing"},
    {"key": "payments", "label": "Payments", "url_name": "payments", "icon": "payments"},
    {"key": "maintenance", "label": "Maintenance", "url_name": "maintenance", "icon": "maintenance"},
    {"key": "expenses", "label": "Expenses", "url_name": "expenses", "icon": "expenses"},
    {"key": "reports", "label": "Reports", "url_name": "reports", "icon": "reports"},
    {"key": "settings", "label": "Settings", "url_name": "settings", "icon": "settings"},
]

SETTINGS_SUBPAGES = {
    "appearance",
    "activity_log",
    "backup_restore",
    "settings",
    "settings_save",
    "appearance_save",
    "backup_now",
}


def app_context(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(user and user.is_authenticated)

    url_name = ""
    match = getattr(request, "resolver_match", None)
    if match is not None:
        url_name = match.url_name or ""

    active_nav = getattr(request, "active_nav", None)
    if active_nav is None:
        if url_name in SETTINGS_SUBPAGES:
            active_nav = "settings"
        elif url_name.startswith(
            (
                "billing",
                "invoice",
                "charge_type",
                "lease_charge",
                "utility_type",
                "meter_reading",
            )
        ):
            active_nav = "billing"
        elif url_name.startswith(("payment", "allocation", "cheque", "statement")):
            active_nav = "payments"
        elif url_name.startswith(("maintenance",)):
            active_nav = "maintenance"
        elif url_name.startswith(("expense",)):
            active_nav = "expenses"
        elif url_name.startswith(("prospect", "vacanc")):
            active_nav = "units"
        elif url_name.startswith(("move_out", "deposit")):
            active_nav = "tenants"
        elif url_name.startswith(("unit", "building", "floor")):
            active_nav = "units"
        elif url_name.startswith(("tenant", "contact", "lease")):
            active_nav = "tenants"
        else:
            active_nav = url_name

    mode = user.theme_mode if is_authenticated else User.MODE_SYSTEM
    palette = user.theme_palette if is_authenticated else "ocean"
    density = user.theme_density if is_authenticated else "comfortable"
    text_size = user.theme_text_size if is_authenticated else "medium"

    return {
        "app_settings": Settings.load(),
        "nav_items": NAV_ITEMS,
        "active_nav": active_nav,
        "theme_mode": mode,
        "theme_palette": palette,
        "theme_density": density,
        "theme_text_size": text_size,
    }
