"""Report filter forms."""

from django import forms
from django.utils import timezone

from core.forms import apply_widget_classes
from property.models import Building, Tenant


class DateRangeForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        initial = dict(kwargs.get("initial") or {})
        today = timezone.localdate()
        initial.setdefault("start_date", today.replace(month=1, day=1))
        initial.setdefault("end_date", today)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date cannot be before the start date.")
        return cleaned


class ArrearsForm(forms.Form):
    as_of = forms.DateField(
        label="As of",
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class OccupancyForm(forms.Form):
    building = forms.ModelChoiceField(
        queryset=Building.objects.all(), required=False, empty_label="All buildings"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class TenantStatementForm(DateRangeForm):
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.order_by("business_name"))

    def __init__(self, *args, **kwargs):
        initial = kwargs.get("initial") or {}
        if "tenant" not in initial:
            kwargs["initial"] = {**initial}
        super().__init__(*args, **kwargs)
