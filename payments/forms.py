"""Payment, receipt and statement import forms."""

from decimal import Decimal

from django import forms
from django.utils import timezone

from core.forms import apply_widget_classes
from payments.models import Payment, StatementImport
from property.models import Tenant


class PaymentForm(forms.Form):
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.order_by("business_name"))
    date_received = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    method = forms.ChoiceField(
        choices=Payment.ENTRY_METHOD_CHOICES,
        initial=Payment.METHOD_BANK,
        label="Method",
        help_text="Rent is recognised only when the money is deposited in the bank account.",
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    reference = forms.CharField(required=False, max_length=100)
    cheque_number = forms.CharField(required=False, max_length=50)
    cheque_bank = forms.CharField(required=False, max_length=100)
    has_withholding = forms.BooleanField(
        label="Tenant withheld tax", required=False
    )
    withholding_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    withholding_cert_no = forms.CharField(required=False, max_length=50)
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["amount"].widget.attrs.update({"step": "0.01", "min": "0"})
        self.fields["withholding_amount"].widget.attrs.update(
            {"step": "0.01", "min": "0"}
        )

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount") or Decimal("0.00")
        withholding = cleaned.get("withholding_amount") or Decimal("0.00")
        if not cleaned.get("has_withholding"):
            withholding = Decimal("0.00")
            cleaned["withholding_amount"] = withholding
        if amount < 0 or withholding < 0:
            raise forms.ValidationError("Amounts cannot be negative.")
        if amount + withholding <= 0:
            raise forms.ValidationError("Enter a cash amount or a withholding amount.")
        if cleaned.get("has_withholding") and withholding <= 0:
            raise forms.ValidationError(
                {"withholding_amount": "Enter the withheld amount."}
            )
        return cleaned


class StatementImportForm(forms.Form):
    source = forms.ChoiceField(
        choices=[(StatementImport.SOURCE_BANK, "Bank")],
        initial=StatementImport.SOURCE_BANK,
    )
    file = forms.FileField(
        help_text="CSV from the bank. Unmatched rows are never posted automatically.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Upload a CSV file.")
        return upload
