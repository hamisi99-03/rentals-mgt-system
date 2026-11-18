from django.contrib import admin

from payments.models import (
    CreditEntry,
    Payment,
    PaymentAllocation,
    StatementImport,
    StatementRow,
)


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ("invoice", "amount", "allocated_at", "is_auto")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "tenant",
        "date_received",
        "method",
        "amount",
        "withholding_amount",
        "status",
    )
    list_filter = ("status", "method", "cheque_status")
    search_fields = ("receipt_number", "tenant__business_name", "reference")
    inlines = [PaymentAllocationInline]


@admin.register(CreditEntry)
class CreditEntryAdmin(admin.ModelAdmin):
    list_display = ("tenant", "entry_date", "amount", "source", "payment", "invoice")
    list_filter = ("source",)


class StatementRowInline(admin.TabularInline):
    model = StatementRow
    extra = 0
    readonly_fields = (
        "tx_date",
        "amount",
        "reference",
        "payer_name",
        "phone",
        "suggested_tenant",
        "suggested_invoice",
        "match_status",
        "payment",
    )


@admin.register(StatementImport)
class StatementImportAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "uploaded_at", "status")
    list_filter = ("source", "status")
    inlines = [StatementRowInline]


@admin.register(StatementRow)
class StatementRowAdmin(admin.ModelAdmin):
    list_display = ("tx_date", "amount", "reference", "match_status", "suggested_tenant")
    list_filter = ("match_status",)
