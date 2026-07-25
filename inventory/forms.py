from django import forms
from django.core.exceptions import ValidationError

from catalog.models import Product, ProductVariant
from growth.models import ProductGrowthData
from inventory.models import StockAdjustment
from merchandising.models import ProductCommerceProfile


def _style_model_form(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css_class = "form-check-input"
        elif isinstance(widget, forms.Select):
            css_class = "form-select"
        else:
            css_class = "form-control"
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{existing} {css_class}".strip()


class ProductCommercialCoreForm(forms.ModelForm):
    """Core public facts reviewed alongside feed and inspection metadata."""

    class Meta:
        model = Product
        fields = (
            "name",
            "sku",
            "short_description",
            "description",
            "price",
            "compare_at_price",
            "track_inventory",
            "stock_quantity",
            "is_published",
            "is_featured",
        )
        widgets = {
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_model_form(self)


class ProductGrowthDataForm(forms.ModelForm):
    """Search, condition and Merchant identity metadata for one product."""

    class Meta:
        model = ProductGrowthData
        fields = (
            "brand",
            "condition",
            "gtin",
            "mpn",
            "google_product_category",
            "custom_label_0",
            "shipping_label",
        )
        widgets = {
            "gtin": forms.TextInput(attrs={"inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_model_form(self)


class ProductCommerceProfileForm(forms.ModelForm):
    """Inspected specifications, delivery facts and Merchant safety controls."""

    VERIFICATION_FIELDS = (
        "identity_verified_at",
        "condition_verified_at",
        "stock_confirmed_at",
        "price_verified_at",
    )

    class Meta:
        model = ProductCommerceProfile
        fields = (
            "processor_family",
            "processor_generation",
            "ram_capacity",
            "ram_type",
            "storage_capacity",
            "storage_type",
            "screen_size",
            "screen_resolution",
            "touchscreen",
            "graphics",
            "operating_system",
            "battery_health_note",
            "keyboard_condition",
            "charger_included",
            "accessories_included",
            "warranty_months",
            "condition_notes",
            "actual_photos",
            "delivery_note",
            "identity_verified_at",
            "condition_verified_at",
            "stock_confirmed_at",
            "price_verified_at",
            "merchant_enabled",
            "merchant_shipping_price",
            "merchant_free_shipping",
        )
        widgets = {
            "condition_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.VERIFICATION_FIELDS:
            self.fields[field_name].widget = forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            )
            self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["merchant_enabled"].disabled = True
        self.fields["merchant_enabled"].help_text = (
            "Merchant approval is locked here. Enable it only after the readiness "
            "audit confirms that every required fact is accurate."
        )
        _style_model_form(self)


class JobStockUseForm(forms.ModelForm):
    """Record parts taken from stock for a repair job (negative quantity_delta)."""

    class Meta:
        model = StockAdjustment
        fields = ("product", "product_variant", "quantity_delta", "note")
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "product_variant": forms.Select(attrs={"class": "form-select"}),
            "quantity_delta": forms.NumberInput(
                attrs={"class": "form-control", "step": "1"}
            ),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_variant"].queryset = ProductVariant.objects.filter(
            is_active=True
        ).select_related("product")
        self.fields["product_variant"].required = False
        self.fields["quantity_delta"].help_text = (
            "Negative number only (e.g. -1 removes one unit from stock)."
        )

    def clean_quantity_delta(self):
        q = self.cleaned_data["quantity_delta"]
        if q >= 0:
            raise ValidationError("Enter a negative quantity to consume stock (e.g. -1).")
        return q

    def clean(self):
        data = super().clean()
        product = data.get("product")
        variant = data.get("product_variant")
        if variant and product and variant.product_id != product.pk:
            raise ValidationError("The variant must belong to the selected product.")
        return data


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ("product", "product_variant", "quantity_delta", "reason", "note")
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "product_variant": forms.Select(attrs={"class": "form-select"}),
            "quantity_delta": forms.NumberInput(attrs={"class": "form-control"}),
            "reason": forms.Select(attrs={"class": "form-select"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_variant"].queryset = ProductVariant.objects.filter(
            is_active=True
        ).select_related("product")
        self.fields["product_variant"].required = False

    def clean(self):
        data = super().clean()
        product = data.get("product")
        variant = data.get("product_variant")
        if variant and product and variant.product_id != product.pk:
            raise ValidationError("The variant must belong to the selected product.")
        return data
