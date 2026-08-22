from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.db import transaction

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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        customers = Customer.objects.filter(email__iexact=email)
        if customers.count() > 1:
            raise forms.ValidationError(
                "This email needs a customer-record review. Please contact customer support."
            )
        customer = customers.first()
        if customer is not None and customer.user_id:
            raise forms.ValidationError(
                "An account already exists for this email. Sign in or reset your password."
            )
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account already exists for this email. Sign in or contact support."
            )
        return email

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Customer accounts must be saved before verification is sent.")
        user = super().save(commit=False)
        email = self.cleaned_data["email"].strip().lower()
        full_name = self.cleaned_data["full_name"].strip()
        phone = (self.cleaned_data.get("phone") or "").strip()
        company_name = (self.cleaned_data.get("company_name") or "").strip()
        user.email = email
        user.first_name = full_name[:150]
        user.is_active = False
        user.save()
        customer = Customer.objects.select_for_update().filter(email__iexact=email).first()
        if customer is None:
            Customer.objects.create(
                email=email,
                name=full_name,
                company_name=company_name,
                phone=phone,
            )
        return user


class CustomerPortalAuthenticationForm(AuthenticationForm):
    """Staff must authenticate through their challenge-protected staff login."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_staff:
            raise forms.ValidationError(
                "Staff accounts must sign in through the staff login page.",
                code="staff_login_required",
            )


class CustomerPortalPasswordResetForm(PasswordResetForm):
    """Keep customer self-service password recovery separate from staff accounts."""

    def get_users(self, email):
        for user in super().get_users(email):
            profile = getattr(user, "customer_profile", None)
            if not user.is_staff and profile is not None:
                yield user


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
