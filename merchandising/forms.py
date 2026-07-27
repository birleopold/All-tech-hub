from __future__ import annotations

from django import forms

from growth.models import ProductGrowthData


class BulkCatalogueEnrichmentForm(forms.Form):
    product_ids = forms.MultipleChoiceField(
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label="Products to update",
    )
    brand = forms.CharField(
        max_length=120,
        required=False,
        help_text="Apply only when every selected product has the same verified brand.",
    )
    condition = forms.ChoiceField(
        required=False,
        choices=(("", "Do not change condition"), *ProductGrowthData.CONDITION_CHOICES),
    )
    warranty_months = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=120,
        help_text="Apply one verified warranty period to all selected products.",
    )
    delivery_note = forms.CharField(
        required=False,
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    shipping_mode = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Do not change Merchant shipping"),
            ("free", "Verified free shipping"),
            ("price", "Use one verified shipping price"),
        ),
    )
    merchant_shipping_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )
    generate_missing_sku = forms.BooleanField(
        required=False,
        help_text="Create a stable internal LEOSOFT SKU only where the SKU is blank.",
    )
    fill_blank_alt_text = forms.BooleanField(
        required=False,
        help_text="Fill only empty gallery alt text using the product name and condition.",
    )
    confirm_actual_photos = forms.BooleanField(
        required=False,
        help_text="Use only after checking that the gallery shows the actual unit or stock.",
    )
    verify_identity = forms.BooleanField(
        required=False,
        help_text="Record that brand, exact model and identifiers were checked.",
    )
    verify_condition = forms.BooleanField(
        required=False,
        help_text="Record that the physical condition was checked.",
    )
    verify_stock = forms.BooleanField(
        required=False,
        help_text="Record that current stock was checked.",
    )
    verify_price = forms.BooleanField(
        required=False,
        help_text="Record that the displayed price was checked.",
    )
    unpublish_out_of_stock = forms.BooleanField(
        required=False,
        help_text="Unpublish selected tracked products that have no sellable base or variant stock.",
    )

    def __init__(self, *args, product_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_ids"].choices = list(product_choices)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs["class"] = "catalogue-bulk-product-options"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned = super().clean()
        shipping_mode = cleaned.get("shipping_mode")
        shipping_price = cleaned.get("merchant_shipping_price")
        if shipping_mode == "price" and shipping_price is None:
            self.add_error(
                "merchant_shipping_price",
                "Enter the verified shipping price for this bulk update.",
            )
        if shipping_mode != "price" and shipping_price is not None:
            self.add_error(
                "merchant_shipping_price",
                "Choose ‘Use one verified shipping price’ before entering a price.",
            )

        operation_fields = (
            "brand",
            "condition",
            "warranty_months",
            "delivery_note",
            "shipping_mode",
            "generate_missing_sku",
            "fill_blank_alt_text",
            "confirm_actual_photos",
            "verify_identity",
            "verify_condition",
            "verify_stock",
            "verify_price",
            "unpublish_out_of_stock",
        )
        if not any(cleaned.get(name) not in (None, "", False) for name in operation_fields):
            raise forms.ValidationError("Choose at least one enrichment action.")
        return cleaned


class SearchConsoleCSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label="Google Search Console CSV",
        help_text="Upload the Queries CSV exported from the Performance report.",
    )
    date_start = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    date_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["csv_file"].widget.attrs.update(
            {"class": "form-control", "accept": ".csv,text/csv"}
        )

    def clean_csv_file(self):
        uploaded = self.cleaned_data["csv_file"]
        if uploaded.size > 2 * 1024 * 1024:
            raise forms.ValidationError("The CSV must be 2 MB or smaller.")
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("Upload a .csv file exported from Search Console.")
        return uploaded

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("date_start")
        end = cleaned.get("date_end")
        if start and end and start > end:
            raise forms.ValidationError("The start date cannot be after the end date.")
        return cleaned
