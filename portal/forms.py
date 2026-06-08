from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from crm.models import Customer, CustomerAddress

User = get_user_model()


class CustomerSignUpForm(UserCreationForm):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    full_name = forms.CharField(
        max_length=200, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    phone = forms.CharField(
        max_length=64, required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    company_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "full_name", "phone", "company_name", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "password1", "password2"):
            self.fields[name].widget.attrs.setdefault("class", "form-control")

    def save(self, commit=True):
        user = super().save(commit=commit)
        email = self.cleaned_data["email"].strip().lower()
        full_name = self.cleaned_data["full_name"].strip()
        phone = (self.cleaned_data.get("phone") or "").strip()
        company_name = (self.cleaned_data.get("company_name") or "").strip()
        Customer.objects.update_or_create(
            email=email,
            defaults={
                "name": full_name,
                "company_name": company_name,
                "phone": phone,
                "user": user,
            },
        )
        return user


class CustomerAddressForm(forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = (
            "label",
            "kind",
            "contact_name",
            "contact_phone",
            "line1",
            "line2",
            "city",
            "region",
            "postal_code",
            "country",
            "is_default",
        )
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "kind": forms.Select(attrs={"class": "form-select"}),
            "contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
            "line1": forms.TextInput(attrs={"class": "form-control"}),
            "line2": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "region": forms.TextInput(attrs={"class": "form-control"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PortalRepairIntakeForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. Laptop won't boot"}
        ),
    )
    device_type = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Laptop, phone, printer…"}),
    )
    device_make = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    device_model = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    serial_number = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    problem_reported = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        label="Describe the problem",
    )

