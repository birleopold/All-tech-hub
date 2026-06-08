from django import forms

from commerce.models import Order
from crm.models import Customer


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "fulfillment_type":
                continue
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")

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
        return customer
