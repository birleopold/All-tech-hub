from django import forms

from commerce.models import Order
from crm.models import Customer
from loyalty.services import add_checkout_consent


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
    marketing_email_opt_in = forms.BooleanField(
        required=False,
        label="Send me occasional LEOSOFT product updates and offers by email.",
    )
    marketing_whatsapp_opt_in = forms.BooleanField(
        required=False,
        label="Send me occasional LEOSOFT product updates and offers by WhatsApp.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def save_customer(self) -> Customer:
        data = self.cleaned_data
        customer, _ = Customer.objects.update_or_create(
            email=data["email"].strip().lower(),
            defaults={
                "name": data["name"].strip(),
                "company_name": (data.get("company_name") or "").strip(),
                "phone": (data.get("phone") or "").strip(),
            },
        )
        add_checkout_consent(
            customer,
            email_marketing=bool(data.get("marketing_email_opt_in")),
            whatsapp_marketing=bool(data.get("marketing_whatsapp_opt_in")),
        )
        return customer
