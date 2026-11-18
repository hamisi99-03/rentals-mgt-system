from django.contrib import admin

from billing.models import (
    ChargeType,
    Invoice,
    InvoiceLine,
    LeaseCharge,
    MeterReading,
    UtilityType,
)


@admin.register(ChargeType)
class ChargeTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "vat_applicable", "is_active")
    list_filter = ("kind", "vat_applicable", "is_active")


@admin.register(LeaseCharge)
class LeaseChargeAdmin(admin.ModelAdmin):
    list_display = ("lease", "charge_type", "amount", "frequency", "start_date", "is_active")
    list_filter = ("frequency", "is_active")


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ("kind", "charge_type", "description", "quantity", "unit_price", "amount", "vat_amount")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "tenant", "unit", "period_start", "due_date", "total", "status")
    list_filter = ("status", "period_start")
    search_fields = ("invoice_number", "tenant__business_name", "unit__code")
    inlines = [InvoiceLineInline]


@admin.register(UtilityType)
class UtilityTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "measure", "rate_per_unit", "is_active")
    list_filter = ("is_active",)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("unit", "utility_type", "reading_date", "reading_value", "previous_value", "consumption", "invoice_line")
    list_filter = ("utility_type",)
    search_fields = ("unit__code",)
