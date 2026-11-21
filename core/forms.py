"""Forms for settings, appearance and login."""

from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from core.models import BRAND_COLOR_CHOICES, Settings, User
from core.recovery import has_recovery_code, verify_recovery_code


def apply_widget_classes(form):
    for field in form.fields.values():
        widget = field.widget
        existing = widget.attrs.get("class", "")
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = f"{existing} checkbox".strip()
        elif isinstance(widget, forms.RadioSelect):
            widget.attrs["class"] = f"{existing} radio".strip()
        elif isinstance(widget, forms.FileInput):
            widget.attrs["class"] = f"{existing} file-input".strip()
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = f"{existing} select".strip()
        else:
            widget.attrs["class"] = f"{existing} input".strip()


class SettingsForm(forms.ModelForm):
    brand_color = forms.ChoiceField(
        choices=BRAND_COLOR_CHOICES,
        required=False,
        label="Company brand colour",
        help_text="Overrides the palette accent across the app and PDFs.",
    )
    auto_lock_minutes = forms.IntegerField(
        min_value=1,
        max_value=240,
        initial=15,
        label="Auto-lock after (minutes)",
        help_text="Inactivity before the screen locks and asks for the password again.",
        widget=forms.NumberInput(attrs={"min": "1", "max": "240"}),
    )

    class Meta:
        model = Settings
        fields = [
            "company_name",
            "address",
            "phone",
            "email",
            "kra_pin",
            "logo",
            "letterhead_text",
            "currency",
            "service_charge_amount",
            "vat_enabled",
            "vat_rate",
            "withholding_rate",
            "invoice_prefix",
            "receipt_prefix",
            "number_separator",
            "number_padding",
            "invoice_due_day",
            "renewal_alert_days",
            "backup_folder",
            "reminder_template",
            "default_palette",
            "brand_color",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "letterhead_text": forms.Textarea(attrs={"rows": 3}),
            "reminder_template": forms.Textarea(attrs={"rows": 4}),
            "vat_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "withholding_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "service_charge_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "number_padding": forms.NumberInput(attrs={"min": "3", "max": "8"}),
            "invoice_due_day": forms.NumberInput(attrs={"min": "1", "max": "28"}),
            "renewal_alert_days": forms.NumberInput(attrs={"min": "1", "max": "365"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        brand_choices = list(BRAND_COLOR_CHOICES)
        current_brand = self.instance.brand_color if self.instance else ""
        if current_brand and current_brand not in dict(BRAND_COLOR_CHOICES):
            brand_choices.append((current_brand, f"Custom ({current_brand})"))
        self.fields["brand_color"].choices = brand_choices
        self.fields["number_separator"].required = False
        self.fields["service_charge_amount"].required = False
        self.fields["vat_enabled"].help_text = (
            "VAT is not yet introduced. Leave this off; invoices will not show VAT lines."
        )
        if user is not None:
            self.fields["auto_lock_minutes"].initial = user.auto_lock_minutes

    def clean_number_separator(self):
        value = self.cleaned_data.get("number_separator") or "-"
        if len(value) > 3:
            raise forms.ValidationError("Use at most three characters.")
        return value

    def clean_service_charge_amount(self):
        value = self.cleaned_data.get("service_charge_amount")
        if value is None:
            if self.instance and self.instance.pk:
                return self.instance.service_charge_amount
            return Decimal("500.00")
        return value

    def clean_vat_rate(self):
        value = self.cleaned_data.get("vat_rate")
        if value is not None and not (0 <= value <= 100):
            raise forms.ValidationError("Enter a percentage between 0 and 100.")
        return value

    def clean_withholding_rate(self):
        value = self.cleaned_data.get("withholding_rate")
        if value is not None and not (0 <= value <= 100):
            raise forms.ValidationError("Enter a percentage between 0 and 100.")
        return value


class AppearanceForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["theme_mode", "theme_palette", "theme_density", "theme_text_size"]
        widgets = {
            "theme_mode": forms.RadioSelect,
            "theme_palette": forms.RadioSelect,
            "theme_density": forms.RadioSelect,
            "theme_text_size": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        controls = {
            "theme_mode": "mode",
            "theme_palette": "palette",
            "theme_density": "density",
            "theme_text_size": "text_size",
        }
        for name, control in controls.items():
            self.fields[name].widget.attrs["data-theme-control"] = control


class PasswordRecoveryForm(forms.Form):
    recovery_code = forms.CharField(
        max_length=50,
        label="Recovery code",
        help_text="The code shown once during setup, for example A1B2C3-D4E5F6-A7B8C9.",
    )
    new_password1 = forms.CharField(
        label="New password", widget=forms.PasswordInput
    )
    new_password2 = forms.CharField(
        label="Confirm new password", widget=forms.PasswordInput
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean_recovery_code(self):
        code = (self.cleaned_data.get("recovery_code") or "").strip()
        if not has_recovery_code():
            raise forms.ValidationError(
                "No recovery code is stored for this installation. Contact technical support."
            )
        if not verify_recovery_code(code):
            raise forms.ValidationError("The recovery code is not correct.")
        return code

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("new_password1")
        password2 = cleaned.get("new_password2")
        if password1 and password2 and password1 != password2:
            self.add_error("new_password2", "The two passwords do not match.")
        return cleaned


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Username", "autofocus": True, "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"placeholder": "Password", "autocomplete": "current-password"}
        )
