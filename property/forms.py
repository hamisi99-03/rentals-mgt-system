"""Forms for property, tenant and lease management."""

from decimal import Decimal

from django import forms
from django.utils import timezone

from core.forms import apply_widget_classes
from core.models import get_current_user
from property.models import (
    Building,
    Document,
    Floor,
    Lease,
    Tenant,
    TenantContact,
    Unit,
)
from property.services import (
    DEFAULT_ESCALATION_INTERVAL_MONTHS,
    ensure_service_charge,
    record_initial_rent,
    record_rent_change,
)


class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ["name", "address", "notes"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2}), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Mwangaza Plaza"


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ["building", "name", "sort_order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Ground floor"
        self.fields["sort_order"].initial = 0
        self.fields["building"].queryset = Building.objects.all()


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ["building", "floor", "code", "size_sqm", "base_rent", "status", "is_active", "notes"]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. A12"}),
            "size_sqm": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "base_rent": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["building"].queryset = Building.objects.all()
        self.fields["floor"].queryset = Floor.objects.select_related("building").all()
        self.fields["status"].help_text = (
            "Occupied is set automatically from the active lease. Use Reserved for a unit held for a prospect."
        )


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = [
            "business_name",
            "trade",
            "id_or_kra_pin",
            "permit_number",
            "vat_applicable",
            "withholding_applicable",
            "primary_unit",
            "status",
            "notes",
        ]
        widgets = {
            "business_name": forms.TextInput(attrs={"placeholder": "e.g. Salon Bella"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["primary_unit"].queryset = Unit.objects.select_related(
            "building", "floor"
        ).all()
        self.fields["primary_unit"].help_text = (
            "Only vacant units can be assigned. Used for document numbering before a lease exists."
        )
        self.fields["vat_applicable"].help_text = (
            "VAT is not yet introduced. Leave this off."
        )


class TenantContactForm(forms.ModelForm):
    class Meta:
        model = TenantContact
        fields = ["name", "role_title", "phone", "email", "is_primary"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["doc_type", "file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class LeaseForm(forms.ModelForm):
    agreement_type = forms.ChoiceField(
        choices=Lease.AGREEMENT_CHOICES,
        initial=Lease.AGREEMENT_LEASE,
        required=False,
        label="Agreement type",
    )

    class Meta:
        model = Lease
        fields = [
            "tenant",
            "unit",
            "agreement_type",
            "start_date",
            "end_date",
            "monthly_rent",
            "deposit_amount",
            "escalation_type",
            "escalation_value",
            "escalation_interval_months",
            "next_escalation_date",
            "status",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "next_escalation_date": forms.DateInput(attrs={"type": "date"}),
            "monthly_rent": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "deposit_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "escalation_value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "escalation_interval_months": forms.NumberInput(attrs={"min": "1"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, allow_reserved=False, **kwargs):
        self.allow_reserved = allow_reserved
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["tenant"].queryset = Tenant.objects.order_by("business_name")
        self.fields["unit"].queryset = Unit.objects.select_related("building", "floor").order_by("code")
        self.fields["escalation_type"].help_text = (
            "Optional rule. Rent is typically reviewed every 24 months."
        )
        if not self.instance.pk:
            self.fields["escalation_interval_months"].initial = (
                DEFAULT_ESCALATION_INTERVAL_MONTHS
            )
        self.fields["next_escalation_date"].help_text = (
            "Invoices whose period starts on or after this date use the escalated rent."
        )
        self.fields["status"].help_text = "Only one active lease per unit may overlap in dates."
        self.fields["agreement_type"].help_text = (
            "Monthly rentals renew automatically until terminated and have no end date."
        )
        self.fields["end_date"].help_text = (
            "Required for a fixed-term lease. Leave blank for a monthly rental."
        )

    def clean(self):
        self.instance._allow_reserved = self.allow_reserved
        cleaned = super().clean()
        agreement = cleaned.get("agreement_type") or Lease.AGREEMENT_LEASE
        cleaned["agreement_type"] = agreement
        if agreement == Lease.AGREEMENT_MONTHLY:
            cleaned["end_date"] = None
        elif not cleaned.get("end_date"):
            self.add_error("end_date", "Enter an end date for a fixed-term lease.")
        if cleaned.get("escalation_type") == Lease.ESCALATION_NONE:
            cleaned["escalation_value"] = Decimal("0.00")
            cleaned["escalation_interval_months"] = None
            cleaned["next_escalation_date"] = None
        elif cleaned.get("escalation_type"):
            if not cleaned.get("escalation_interval_months"):
                cleaned["escalation_interval_months"] = (
                    DEFAULT_ESCALATION_INTERVAL_MONTHS
                )
            if not cleaned.get("next_escalation_date") and cleaned.get("start_date"):
                from billing.services import add_months

                cleaned["next_escalation_date"] = add_months(
                    cleaned["start_date"], DEFAULT_ESCALATION_INTERVAL_MONTHS
                )
        return cleaned

    def save(self, commit=True):
        lease = super().save(commit=False)
        is_new = lease.pk is None
        old_rent = None
        if not is_new:
            old_rent = (
                Lease.objects.filter(pk=lease.pk)
                .values_list("monthly_rent", flat=True)
                .first()
            )
        if not commit:
            return lease
        lease.save()
        user = get_current_user()
        if is_new:
            record_initial_rent(lease, changed_by=user)
            ensure_service_charge(lease)
        elif old_rent is not None and old_rent != lease.monthly_rent:
            record_rent_change(lease, old_rent, changed_by=user)
        return lease


class TerminateLeaseForm(forms.Form):
    terminated_on = forms.DateField(
        label="Termination date",
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    termination_reason = forms.CharField(
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)


class ImportForm(forms.Form):
    file = forms.FileField(
        label="Excel workbook",
        help_text="Use the downloaded template. Nothing is committed if any row has an error.",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Upload an .xlsx workbook.")
        return upload
