from django.contrib import admin

from property.models import (
    Building,
    Document,
    Floor,
    Lease,
    LeaseRentHistory,
    Tenant,
    TenantContact,
    Unit,
)


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("name", "address")
    search_fields = ("name", "address")


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "sort_order")
    list_filter = ("building",)
    search_fields = ("name", "building__name")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "building", "floor", "status", "base_rent", "is_active")
    list_filter = ("status", "building", "floor", "is_active")
    search_fields = ("code", "building__name")


class TenantContactInline(admin.TabularInline):
    model = TenantContact
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("business_name", "trade", "primary_unit", "status")
    list_filter = ("status",)
    search_fields = ("business_name", "trade", "id_or_kra_pin")
    inlines = [TenantContactInline]


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("tenant", "unit", "start_date", "end_date", "monthly_rent", "status")
    list_filter = ("status", "escalation_type")
    search_fields = ("tenant__business_name", "unit__code")
    date_hierarchy = "start_date"


@admin.register(LeaseRentHistory)
class LeaseRentHistoryAdmin(admin.ModelAdmin):
    list_display = ("lease", "effective_date", "old_rent", "new_rent", "reason")
    list_filter = ("reason",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "content_object", "uploaded_at", "uploaded_by")
    list_filter = ("doc_type",)
