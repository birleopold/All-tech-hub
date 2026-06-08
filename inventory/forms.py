from django import forms
from django.core.exceptions import ValidationError

from catalog.models import ProductVariant
from inventory.models import StockAdjustment


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
