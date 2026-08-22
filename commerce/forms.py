from decimal import Decimal

from django import forms

from commerce.models import Order
from crm.models import Customer
from loyalty.services import add_checkout_consent
from merchandising.models import DeliveryZone


class CheckoutForm(forms.Form):
    name = forms.CharField(max_length=200)
    email = forms.EmailField()
    phone = forms.CharField(max_length=64, required=False)
    company_name = forms.CharField(max_length=200, required=False)
    billing_address = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Street, city, postal code",
    )
    shipping_address = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Leave blank if same as billing.",
    )
    customer_note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        required=False,
    )
    fulfillment_type = forms.ChoiceField(
        choices=Order.FULFILLMENT_CHOICES,
        initial=Order.FULFILLMENT_DELIVERY,
        widget=forms.RadioSelect,
        label="How would you like to receive your order?",
    )
    delivery_zone = forms.ModelChoiceField(
        queryset=DeliveryZone.objects.none(),
        required=False,
        empty_label="Choose your delivery area",
        label="Delivery area",
        help_text="Delivery charges apply only when delivery is selected.",
    )
    marketing_email_opt_in = forms.BooleanField(
        required=False,
        label="Send me occasional LEOSOFT product updates and offers by email.",
    )
    marketing_whatsapp_opt_in = forms.BooleanField(
        required=False,
        label="Send me occasional LEOSOFT product updates and offers by WhatsApp.",
    )

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        self.fields["delivery_zone"].queryset = DeliveryZone.objects.filter(is_active=True)
        self.fields["delivery_zone"].label_from_instance = lambda zone: (
            f"{zone.name} — {zone.areas}"
            + (f" · from {zone.fee_from:,.0f}" if zone.fee_from is not None else "")
            + (f" · {zone.lead_time}" if zone.lead_time else "")
        )
        self.delivery_zones_available = self.fields["delivery_zone"].queryset.exists()
        autocomplete = {
            "name": "name",
            "email": "email",
            "phone": "tel",
            "company_name": "organization",
            "billing_address": "billing street-address",
            "shipping_address": "shipping street-address",
            "customer_note": "off",
        }
        for name, field in self.fields.items():
            if name == "fulfillment_type":
                continue
            if name in {"marketing_email_opt_in", "marketing_whatsapp_opt_in"}:
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
                field.widget.attrs.setdefault("autocomplete", autocomplete.get(name, "off"))
            if name == "phone":
                field.widget.attrs.setdefault("inputmode", "tel")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Customer.objects.filter(email__iexact=email).count() > 1:
            raise forms.ValidationError(
                "This customer email needs a support review before an order can be placed."
            )
        profile = getattr(self.request_user, "customer_profile", None)
        if profile is not None and profile.email.strip().lower() != email:
            raise forms.ValidationError(
                "Use the verified email address connected to your customer account."
            )
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("fulfillment_type") == Order.FULFILLMENT_DELIVERY:
            if self.delivery_zones_available and not cleaned_data.get("delivery_zone"):
                self.add_error("delivery_zone", "Choose the area where we should deliver.")
        else:
            cleaned_data["delivery_zone"] = None
        return cleaned_data

    @property
    def delivery_fee(self) -> Decimal:
        zone = self.cleaned_data.get("delivery_zone")
        if self.cleaned_data.get("fulfillment_type") != Order.FULFILLMENT_DELIVERY:
            return Decimal("0.00")
        if zone is None or zone.fee_from is None:
            return Decimal("0.00")
        return zone.fee_from

    def save_customer(self) -> Customer:
        data = self.cleaned_data
        email = data["email"].strip().lower()
        customer = Customer.objects.select_for_update().filter(email__iexact=email).first()
        created = customer is None
        if created:
            customer = Customer.objects.create(
                email=email,
                name=data["name"].strip(),
                company_name=(data.get("company_name") or "").strip(),
                phone=(data.get("phone") or "").strip(),
            )
        account_owner = (
            self.request_user is not None
            and getattr(self.request_user, "is_authenticated", False)
            and customer.user_id == self.request_user.pk
        )
        if created or account_owner:
            add_checkout_consent(
                customer,
                email_marketing=bool(data.get("marketing_email_opt_in")),
                whatsapp_marketing=bool(data.get("marketing_whatsapp_opt_in")),
            )
        return customer
