"""Operations forms: deposits, move-outs, prospects, maintenance and expenses."""

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from billing.models import MeterReading
from core.forms import apply_widget_classes
from operations.models import (
    Deposit,
    Expense,
    ExpenseCategory,
    MaintenanceRequest,
    MoveOut,
    MoveOutItem,
    Prospect,
)
from property.models import Tenant, Unit


class DepositForm(forms.ModelForm):
    class Meta:
        model = Deposit
        fields = ["amount_received", "received_date"]
        widgets = {
            "amount_received": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "received_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        if not self.instance.pk:
            self.fields["received_date"].initial = timezone.localdate()


class MoveOutForm(forms.ModelForm):
    class Meta:
        model = MoveOut
        fields = ["notice_date", "move_out_date", "settlement_notes"]
        widgets = {
            "notice_date": forms.DateInput(attrs={"type": "date"}),
            "move_out_date": forms.DateInput(attrs={"type": "date"}),
            "settlement_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, utility_types=None, lease=None, **kwargs):
        self.utility_types = list(utility_types or [])
        self.lease = lease
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.reading_fields = []
        for utility_type in self.utility_types:
            name = f"reading_{utility_type.pk}"
            self.fields[name] = forms.DecimalField(
                required=False,
                min_value=Decimal("0"),
                max_digits=12,
                decimal_places=2,
                label=f"{utility_type.name} reading ({utility_type.measure})",
            )
            self.fields[name].widget.attrs["class"] = "input"
            self.fields[name].widget.attrs.update({"step": "0.01", "min": "0"})
            self.reading_fields.append((utility_type, name))
        self.reading_bound_fields = [
            (utility_type, self[name]) for utility_type, name in self.reading_fields
        ]

    def clean(self):
        cleaned = super().clean()
        move_out_date = cleaned.get("move_out_date")
        lease = self.lease or (
            self.instance.lease if self.instance.lease_id else None
        )
        unit = lease.unit if lease else None
        for utility_type, name in self.reading_fields:
            value = cleaned.get(name)
            if value is None or not move_out_date or unit is None:
                continue
            previous = (
                MeterReading.objects.filter(
                    unit=unit,
                    utility_type=utility_type,
                    reading_date__lt=move_out_date,
                )
                .order_by("-reading_date", "-id")
                .first()
            )
            if previous and value < previous.reading_value:
                self.add_error(
                    name,
                    f"Cannot be below the previous reading of {previous.reading_value}.",
                )
        return cleaned

    def reading_values(self):
        return [
            (utility_type, self.cleaned_data.get(name))
            for utility_type, name in self.reading_fields
        ]


class MoveOutItemForm(forms.ModelForm):
    CONDITION_CHOICES = [
        ("ok", "OK"),
        ("damaged", "Damaged"),
        ("missing", "Missing"),
        ("not_checked", "Not checked"),
    ]

    condition = forms.ChoiceField(choices=CONDITION_CHOICES)

    class Meta:
        model = MoveOutItem
        fields = ["item", "condition", "damage_cost", "notes"]
        widgets = {
            "damage_cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "notes": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


MoveOutItemFormSet = inlineformset_factory(
    MoveOut,
    MoveOutItem,
    form=MoveOutItemForm,
    fields=["item", "condition", "damage_cost", "notes"],
    extra=0,
    can_delete=False,
)


class ProspectForm(forms.ModelForm):
    class Meta:
        model = Prospect
        fields = [
            "name",
            "business",
            "phone",
            "email",
            "interested_unit",
            "status",
            "follow_up_date",
            "notes",
        ]
        widgets = {
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["interested_unit"].queryset = Unit.objects.filter(
            is_active=True
        ).order_by("code")


class MaintenanceRequestForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = [
            "unit",
            "tenant",
            "title",
            "description",
            "priority",
            "status",
            "reported_date",
            "completed_date",
            "cost",
        ]
        widgets = {
            "reported_date": forms.DateInput(attrs={"type": "date"}),
            "completed_date": forms.DateInput(attrs={"type": "date"}),
            "cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["reported_date"].initial = timezone.localdate()
        self.fields["unit"].queryset = Unit.objects.select_related(
            "building", "floor"
        ).order_by("code")
        self.fields["tenant"].queryset = Tenant.objects.order_by("business_name")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == MaintenanceRequest.STATUS_DONE and not cleaned.get(
            "completed_date"
        ):
            cleaned["completed_date"] = timezone.localdate()
        return cleaned


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "expense_date",
            "amount",
            "payee",
            "description",
            "payment_method",
            "reference",
            "maintenance_request",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        if not self.instance.pk:
            self.fields["expense_date"].initial = timezone.localdate()
        self.fields["category"].queryset = ExpenseCategory.objects.all()
        self.fields["maintenance_request"].queryset = MaintenanceRequest.objects.all()
