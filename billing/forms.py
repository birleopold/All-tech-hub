from django import forms
from django.core.exceptions import ValidationError

from billing.models import CommercialDocument, CommercialLine, DocumentPayment
from catalog.models import Product, ProductVariant
from core.models import CompanySettings


class CommercialDocumentForm(forms.ModelForm):
    class Meta:
        model = CommercialDocument
        fields = (
            "doc_type",
            "customer",
            "title",
            "issue_date",
            "due_date",
            "status",
            "notes",
            "terms",
            "tax_rate",
            "order",
            "quote_requires_internal_approval",
            "quote_requires_customer_acceptance",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "terms": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("doc_type", "customer", "status", "order"):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-select")
        for name in ("issue_date", "due_date", "tax_rate"):
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("class", "form-control")
        if "quote_requires_internal_approval" in self.fields:
            self.fields["quote_requires_internal_approval"].widget.attrs.setdefault(
                "class", "form-check-input"
            )
            self.fields["quote_requires_internal_approval"].label = (
                "Require internal approval before converting this quotation"
            )
        if "quote_requires_customer_acceptance" in self.fields:
            self.fields["quote_requires_customer_acceptance"].widget.attrs.setdefault(
                "class", "form-check-input"
            )
            self.fields["quote_requires_customer_acceptance"].label = (
                "Require customer acceptance via secure link before converting"
            )
        if self.instance.pk and self.instance.doc_type != CommercialDocument.TYPE_QUOTE:
            self.fields.pop("quote_requires_internal_approval", None)
            self.fields.pop("quote_requires_customer_acceptance", None)
        if not self.instance.pk:
            self.fields["tax_rate"].initial = CompanySettings.load().default_tax_rate


class CommercialLineForm(forms.ModelForm):
    class Meta:
        model = CommercialLine
        fields = ("product", "product_variant", "description", "quantity", "unit_price")
        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_published=True)
        self.fields["product"].required = False
        self.fields["product"].widget.attrs.setdefault("class", "form-select line-product")
        vq = ProductVariant.objects.filter(is_active=True).select_related("product").order_by(
            "product__name", "sort_order", "id"
        )
        self.fields["product_variant"] = forms.ModelChoiceField(
            queryset=vq,
            required=False,
            widget=forms.Select(attrs={"class": "form-select line-variant"}),
            label="Option",
        )
        self.fields["product_variant"].label_from_instance = (
            lambda v: f"{v.product.name} — {v.name} ({v.price})"
        )

    def clean(self):
        cleaned_data = super().clean()
        prod = cleaned_data.get("product")
        var = cleaned_data.get("product_variant")
        if var and prod and var.product_id != prod.pk:
            raise ValidationError(
                {"product_variant": "The option must belong to the selected product."}
            )
        if var and not prod:
            cleaned_data["product"] = var.product
        return cleaned_data


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = DocumentPayment
        fields = ("amount", "method", "reference", "note")
        widgets = {
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "method": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
