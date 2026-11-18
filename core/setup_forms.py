"""First-run setup form."""

from django import forms
from django.contrib.auth.password_validation import validate_password

from core.forms import apply_widget_classes
from core.models import HEX_COLOR_VALIDATOR, User


class SetupForm(forms.Form):
    company_name = forms.CharField(max_length=150, initial="Rental Manager")
    address = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    phone = forms.CharField(max_length=30, required=False)
    email = forms.EmailField(required=False)
    kra_pin = forms.CharField(max_length=30, required=False)
    logo = forms.ImageField(required=False)
    letterhead_text = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    backup_folder = forms.CharField(
        max_length=500,
        required=False,
        help_text="USB or external drive folder. Leave blank to use the app's data folder.",
    )
    owner_username = forms.CharField(max_length=150, label="Owner username")
    owner_full_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)
    default_palette = forms.ChoiceField(
        choices=User.PALETTE_CHOICES, initial="ocean", label="Theme palette"
    )
    brand_color = forms.CharField(max_length=7, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_widget_classes(self)

    def clean_owner_username(self):
        username = self.cleaned_data["owner_username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two passwords do not match.")
        if password2:
            validate_password(password2)
        return password2

    def clean_brand_color(self):
        value = (self.cleaned_data.get("brand_color") or "").strip()
        if value:
            HEX_COLOR_VALIDATOR(value)
        return value
