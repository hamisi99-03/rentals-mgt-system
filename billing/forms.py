"""Billing forms: run, charges, utility types and meter readings."""

from django import forms

from billing.models import ChargeType, LeaseCharge, MeterReading, UtilityType
from billing.services import default_due_date, parse_period
from core.forms import apply_widget_classes
from core.models import Settings


class BillingRunForm(forms.Form):
    period = forms.CharField(
        label="Period",
        max_length=7,
        widget=forms.TextInput(attrs={"placeholder": "2026-11", "class": "input"}),
        help_text="Month to invoice, in YYYY-MM format.",
    )
    due_date = forms.DateField(
        label="Due date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean_period(self):
        value = self.cleaned_data["period"].strip()
        try:
            self.period_start, self.period_end = parse_period(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return value

    def clean(self):
        cleaned = super().clean()
        period_start = getattr(self, "period_start", None)
        if period_start and not cleaned.get("due_date"):
            cleaned["due_date"] = default_due_date(period_start, Settings.load())
        return cleaned


class ChargeTypeForm(forms.ModelForm):
    class Meta:
        model = ChargeType
        fields = ["name", "kind", "vat_applicable", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class LeaseChargeForm(forms.ModelForm):
    class Meta:
        model = LeaseCharge
        fields = ["charge_type", "amount", "frequency", "start_date", "end_date", "is_active"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["charge_type"].queryset = ChargeType.objects.all()


class UtilityTypeForm(forms.ModelForm):
    class Meta:
        model = UtilityType
        fields = ["name", "measure", "rate_per_unit", "is_active"]
        widgets = {
            "measure": forms.TextInput(attrs={"placeholder": "m3, kWh or kg"}),
            "rate_per_unit": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class MeterReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ["unit", "utility_type", "reading_date", "reading_value"]
        widgets = {
            "reading_date": forms.DateInput(attrs={"type": "date"}),
            "reading_value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["utility_type"].queryset = UtilityType.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        utility = cleaned.get("utility_type")
        reading_date = cleaned.get("reading_date")
        reading_value = cleaned.get("reading_value")
        if unit and utility and reading_date and reading_value is not None:
            previous = (
                MeterReading.objects.filter(
                    unit=unit,
                    utility_type=utility,
                    reading_date__lt=reading_date,
                )
                .exclude(pk=self.instance.pk)
                .order_by("-reading_date", "-id")
                .first()
            )
            if previous and reading_value < previous.reading_value:
                self.add_error(
                    "reading_value",
                    f"Reading cannot be below the previous reading of {previous.reading_value}.",
                )
        return cleaned
