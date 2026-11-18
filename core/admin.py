from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import AuditLog, BackupLog, NumberSequence, Settings, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "full_name", "is_active", "last_login")
    list_filter = ("is_active",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Profile",
            {
                "fields": (
                    "full_name",
                    "phone",
                    "auto_lock_minutes",
                    "created_at",
                    "updated_at",
                    "created_by",
                )
            },
        ),
        (
            "Theme",
            {"fields": ("theme_mode", "theme_palette", "theme_density", "theme_text_size")},
        ),
    )
    readonly_fields = ("created_at", "updated_at", "created_by")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Company", {"fields": ("company_name", "address", "phone", "email", "kra_pin", "logo", "letterhead_text", "currency")}),
        ("Tax", {"fields": ("vat_enabled", "vat_rate", "withholding_rate")}),
        ("Numbering", {"fields": ("invoice_prefix", "receipt_prefix", "number_separator", "number_padding", "invoice_due_day", "renewal_alert_days")}),
        ("Backup and reminders", {"fields": ("backup_folder", "reminder_template")}),
        ("Appearance", {"fields": ("default_palette", "brand_color")}),
    )
    readonly_fields = ("created_at", "updated_at", "created_by")

    def has_add_permission(self, request):
        return not Settings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "model", "object_repr")
    list_filter = ("action",)
    search_fields = ("model", "object_repr", "user__username")
    readonly_fields = (
        "timestamp",
        "user",
        "action",
        "model",
        "object_id",
        "object_repr",
        "changes",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "result", "destination_path", "size_bytes")
    list_filter = ("result",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "unit", "last_value")
    list_filter = ("doc_type",)
    readonly_fields = ("last_value",)
