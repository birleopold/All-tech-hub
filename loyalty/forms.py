from django import forms

from loyalty.models import CustomerMarketingPreference


class MarketingPreferenceForm(forms.Form):
    email_marketing = forms.BooleanField(
        required=False,
        label="Email product updates and occasional offers",
    )
    whatsapp_marketing = forms.BooleanField(
        required=False,
        label="WhatsApp product updates and occasional offers",
    )
    product_updates = forms.BooleanField(
        required=False,
        label="Product and service updates",
    )
    special_offers = forms.BooleanField(
        required=False,
        label="Special offers and promotions",
    )

    def __init__(self, *args, preference: CustomerMarketingPreference | None = None, **kwargs):
        if preference is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "email_marketing": preference.email_marketing,
                "whatsapp_marketing": preference.whatsapp_marketing,
                "product_updates": preference.product_updates,
                "special_offers": preference.special_offers,
            }
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email_marketing") and not cleaned.get("whatsapp_marketing"):
            cleaned["product_updates"] = False
            cleaned["special_offers"] = False
        return cleaned
