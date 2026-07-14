from django import forms

from catalog.models import Product
from growth.models import (
    Ambassador,
    ContentAsset,
    DistributionGroup,
    GrowthSettings,
    ProductGrowthData,
    StockAlertSubscription,
)
from marketing.models import MarketingCampaign


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"


class GrowthSettingsForm(BootstrapModelForm):
    class Meta:
        model = GrowthSettings
        exclude = ()


class ProductGrowthDataForm(BootstrapModelForm):
    class Meta:
        model = ProductGrowthData
        fields = (
            "product",
            "brand",
            "gtin",
            "mpn",
            "condition",
            "google_product_category",
            "custom_label_0",
            "shipping_label",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Product.objects.filter(
            is_published=True,
            kind=Product.KIND_PHYSICAL,
        ).order_by("name")
        if self.instance and self.instance.pk:
            queryset = Product.objects.filter(
                pk=self.instance.product_id
            ) | queryset.exclude(growth_data__isnull=False)
        else:
            queryset = queryset.filter(growth_data__isnull=True)
        self.fields["product"].queryset = queryset.distinct()


class SavedCartOptInForm(forms.Form):
    name = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Your name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"})
    )
    phone = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone or WhatsApp number"}),
    )
    consent = forms.BooleanField(
        label="Save this cart and send me reminder emails.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class StockAlertForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"})
    )
    phone = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone or WhatsApp number"}),
    )
    alert_type = forms.ChoiceField(
        choices=StockAlertSubscription.ALERT_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    target_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("alert_type") == StockAlertSubscription.ALERT_PRICE_DROP
            and cleaned.get("target_price") is None
        ):
            self.add_error("target_price", "Enter the price at which you want to be notified.")
        return cleaned


class DistributionGroupForm(BootstrapModelForm):
    class Meta:
        model = DistributionGroup
        fields = (
            "platform",
            "name",
            "url",
            "audience",
            "rules",
            "best_posting_times",
            "tracking_link",
            "last_posted_at",
            "is_active",
            "notes",
        )
        widgets = {
            "rules": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "last_posted_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }


class AmbassadorForm(BootstrapModelForm):
    class Meta:
        model = Ambassador
        fields = (
            "name",
            "code",
            "email",
            "phone",
            "destination_url",
            "commission_type",
            "commission_value",
            "is_active",
            "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class ContentAssetGeneratorForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_published=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    campaign = forms.ModelChoiceField(
        queryset=MarketingCampaign.objects.all().order_by("-created_at"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    asset_types = forms.MultipleChoiceField(
        choices=ContentAsset.TYPE_CHOICES,
        required=False,
        help_text="Leave all unchecked to generate the full six-asset pack.",
        widget=forms.CheckboxSelectMultiple,
    )
