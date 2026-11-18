from django.contrib import admin

from operations.models import (
    Deposit,
    Expense,
    ExpenseCategory,
    MaintenanceRequest,
    MoveOut,
    MoveOutItem,
    Prospect,
)


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ("lease", "amount_received", "received_date", "status")
    list_filter = ("status",)


class MoveOutItemInline(admin.TabularInline):
    model = MoveOutItem
    extra = 0


@admin.register(MoveOut)
class MoveOutAdmin(admin.ModelAdmin):
    list_display = ("lease", "move_out_date", "deposit_held", "refund_amount", "status")
    list_filter = ("status",)
    inlines = [MoveOutItemInline]


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "phone", "interested_unit", "status", "follow_up_date")
    list_filter = ("status",)
    search_fields = ("name", "business", "phone")


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "unit", "priority", "status", "reported_date", "cost")
    list_filter = ("status", "priority")
    search_fields = ("title", "unit__code")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("payee", "category", "expense_date", "amount")
    list_filter = ("category", "payment_method")
    search_fields = ("payee", "description", "reference")
