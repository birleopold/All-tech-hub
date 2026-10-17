from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet

from billing.models import (
    AccountPayment,
    CommercialDocument,
    CommercialLine,
    DocumentPayment,
    DocumentTemplate,
    PaymentRefund,
)
from catalog.models import Product, ProductVariant
from core.models import CompanySettings


class CommercialDocumentForm(forms.ModelForm):
    save_customer_to_crm = forms.BooleanField(
        required=False,
        label="Save this walk-in as a CRM customer",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    template = forms.ModelChoiceField(
        queryset=DocumentTemplate.objects.none(),
        required=False,
        label="Start from template",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    template_name = forms.CharField(
        required=False,
        max_length=160,
        label="Template name",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Standard installation quote"}
        ),
    )

    class Meta:
        model = CommercialDocument
        fields = (
            "doc_type",
            "customer",
            "customer_name",
            "customer_company",
            "customer_email",
            "customer_phone",
            "customer_tax_reference",
            "customer_address",
            "title",
            "issue_date",
            "due_date",
            "status",
            "notes",
            "terms",
            "pricing_mode",
            "tax_rate",
            "tax_exempt",
            "tax_exemption_reason",
            "discount_type",
            "discount_value",
            "shipping_amount",
            "other_charges_label",
            "other_charges",
            "withholding_tax_rate",
            "amount_tendered",
            "receipt_payment_method",
            "receipt_payment_reference",
            "hide_prices",
            "salesperson",
            "location",
            "vehicle_reference",
            "contact_reference",
            "order",
            "quote_requires_internal_approval",
            "quote_requires_customer_acceptance",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "customer_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Required"}
            ),
            "customer_company": forms.TextInput(attrs={"class": "form-control"}),
            "customer_email": forms.EmailInput(attrs={"class": "form-control"}),
            "customer_phone": forms.TextInput(attrs={"class": "form-control"}),
            "customer_tax_reference": forms.TextInput(attrs={"class": "form-control"}),
            "customer_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "terms": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "issue_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "due_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "tax_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                }
            ),
            "discount_value": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "shipping_amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "other_charges": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "withholding_tax_rate": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}
            ),
            "amount_tendered": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "receipt_payment_method": forms.Select(attrs={"class": "form-select"}),
            "receipt_payment_reference": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "tax_exemption_reason": forms.TextInput(attrs={"class": "form-control"}),
            "other_charges_label": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "vehicle_reference": forms.TextInput(attrs={"class": "form-control"}),
            "contact_reference": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].required = False
        self.fields["customer"].label = "Existing customer (optional)"
        self.fields["customer"].help_text = (
            "Select a CRM customer to fill the details below, or leave blank for a walk-in."
        )
        self.fields["customer_name"].required = False
        self.fields["customer_name"].label = "Customer / walk-in name"
        self.fields["customer_company"].label = "Company (optional)"
        self.fields["customer_tax_reference"].label = "Tax reference / TIN"
        self.fields["customer_address"].label = "Billing address"
        self.fields["template"].queryset = DocumentTemplate.objects.filter(
            is_active=True
        )
        self.fields["pricing_mode"].required = False
        self.fields["discount_type"].required = False
        for name in (
            "discount_value",
            "shipping_amount",
            "other_charges",
            "withholding_tax_rate",
            "amount_tendered",
        ):
            self.fields[name].required = False
        for name in (
            "doc_type",
            "customer",
            "status",
            "order",
            "pricing_mode",
            "discount_type",
            "salesperson",
        ):
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
        if not self.instance.pk:
            self.fields["tax_rate"].initial = CompanySettings.load().default_tax_rate
            selected_type = self.data.get("doc_type") or self.initial.get("doc_type")
            if selected_type == CommercialDocument.TYPE_RECEIPT:
                self.fields["status"].choices = [
                    (CommercialDocument.STATUS_ISSUED, "Issued"),
                    (CommercialDocument.STATUS_PAID, "Paid"),
                ]
                self.fields["status"].initial = CommercialDocument.STATUS_ISSUED
            else:
                self.fields["status"].choices = [
                    (CommercialDocument.STATUS_DRAFT, "Draft"),
                    (CommercialDocument.STATUS_ISSUED, "Issued"),
                ]
        self.fields["title"].widget.attrs.setdefault(
            "placeholder", "Optional heading shown on the document"
        )
        self.fields["notes"].widget.attrs.setdefault(
            "placeholder", "Internal or customer-facing notes"
        )
        self.fields["terms"].widget.attrs.setdefault(
            "placeholder", "Payment, delivery, warranty, or validity terms"
        )
        self.fields["order"].help_text = (
            "Optional. Leave blank for counter sales, walk-ins, and standalone documents."
        )
        self.fields["discount_value"].help_text = (
            "Percentage or fixed amount according to the selected discount type."
        )
        self.fields["tax_exempt"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["hide_prices"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["salesperson"].required = False
        self.fields["receipt_payment_method"].required = False

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["pricing_mode"] = (
            cleaned_data.get("pricing_mode")
            or CommercialDocument.PRICING_EXCLUSIVE
        )
        cleaned_data["discount_type"] = (
            cleaned_data.get("discount_type")
            or CommercialDocument.DISCOUNT_PERCENT
        )
        for name in (
            "discount_value",
            "shipping_amount",
            "other_charges",
            "withholding_tax_rate",
            "amount_tendered",
        ):
            cleaned_data[name] = cleaned_data.get(name) or Decimal("0")
        issue_date = cleaned_data.get("issue_date")
        due_date = cleaned_data.get("due_date")
        tax_rate = cleaned_data.get("tax_rate")
        withholding_rate = cleaned_data.get("withholding_tax_rate")
        discount_value = cleaned_data.get("discount_value")
        discount_type = cleaned_data.get("discount_type")
        customer = cleaned_data.get("customer")
        customer_name = (cleaned_data.get("customer_name") or "").strip()
        order = cleaned_data.get("order")
        doc_type = cleaned_data.get("doc_type")

        if issue_date and due_date and due_date < issue_date:
            self.add_error("due_date", "Due date cannot be before the issue date.")
        if tax_rate is not None and not 0 <= tax_rate <= 100:
            self.add_error("tax_rate", "Tax rate must be between 0 and 100.")
        if withholding_rate is not None and not 0 <= withholding_rate <= 100:
            self.add_error(
                "withholding_tax_rate", "Withholding rate must be between 0 and 100."
            )
        if discount_value is not None and discount_value < 0:
            self.add_error("discount_value", "Discount cannot be negative.")
        if (
            discount_type == CommercialDocument.DISCOUNT_PERCENT
            and discount_value is not None
            and discount_value > 100
        ):
            self.add_error("discount_value", "Percentage discount cannot exceed 100%.")
        if order and customer and order.customer_id != customer.pk:
            self.add_error("order", "This order belongs to a different customer.")
        elif order and not customer:
            customer = order.customer
            cleaned_data["customer"] = customer
        if customer:
            snapshot_defaults = {
                "customer_name": customer.name,
                "customer_company": customer.company_name,
                "customer_email": customer.email,
                "customer_phone": customer.phone,
                "customer_tax_reference": customer.tax_reference,
            }
            for field, value in snapshot_defaults.items():
                if not cleaned_data.get(field):
                    cleaned_data[field] = value or ""
            customer_name = cleaned_data["customer_name"]
        if not customer_name:
            self.add_error(
                "customer_name",
                "Enter a customer or walk-in name, or select an existing customer.",
            )
        if doc_type != CommercialDocument.TYPE_QUOTE:
            cleaned_data["quote_requires_internal_approval"] = False
            cleaned_data["quote_requires_customer_acceptance"] = False
        if doc_type in (
            CommercialDocument.TYPE_RECEIPT,
            CommercialDocument.TYPE_DELIVERY_NOTE,
            CommercialDocument.TYPE_CREDIT_NOTE,
        ):
            cleaned_data["due_date"] = None
        if doc_type == CommercialDocument.TYPE_RECEIPT and cleaned_data.get(
            "status"
        ) not in (
            CommercialDocument.STATUS_ISSUED,
            CommercialDocument.STATUS_PAID,
        ):
            cleaned_data["status"] = CommercialDocument.STATUS_ISSUED
        if cleaned_data.get("tax_exempt") and not (
            cleaned_data.get("tax_exemption_reason") or ""
        ).strip():
            self.add_error(
                "tax_exemption_reason", "Give a reason for tax exemption."
            )
        if cleaned_data.get("save_customer_to_crm") and customer:
            self.add_error(
                "save_customer_to_crm",
                "This document is already linked to an existing customer.",
            )
        return cleaned_data


class CommercialLineForm(forms.ModelForm):
    class Meta:
        model = CommercialLine
        fields = (
            "product",
            "product_variant",
            "source_type",
            "description",
            "sku",
            "serial_number",
            "warranty",
            "line_note",
            "section",
            "sort_order",
            "quantity",
            "unit_price",
            "unit_cost",
            "supplier_name",
            "source_reference",
            "discount_type",
            "discount_value",
            "tax_rate",
            "tax_exempt",
        )
        widgets = {
            "description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Item or service description"}
            ),
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "unit_price": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "unit_cost": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "discount_value": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
            "tax_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                    "placeholder": "Document rate",
                }
            ),
            "sort_order": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["quantity"] = None
            for name in (
                "source_type",
                "discount_type",
                "unit_cost",
                "discount_value",
                "sort_order",
                "tax_exempt",
            ):
                self.initial[name] = None
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
        for name in ("source_type", "discount_type"):
            self.fields[name].widget.attrs.setdefault("class", "form-select")
            self.fields[name].required = False
        for name in ("sort_order", "unit_cost", "discount_value"):
            self.fields[name].required = False
        for name in (
            "sku",
            "serial_number",
            "warranty",
            "line_note",
            "section",
            "supplier_name",
            "source_reference",
        ):
            self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["tax_exempt"].widget.attrs.setdefault("class", "form-check-input")
        self.fields["product_variant"].label_from_instance = (
            lambda v: f"{v.product.name} — {v.name} ({v.price})"
        )

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["source_type"] = (
            cleaned_data.get("source_type") or CommercialLine.SOURCE_CUSTOM
        )
        cleaned_data["discount_type"] = (
            cleaned_data.get("discount_type")
            or CommercialDocument.DISCOUNT_PERCENT
        )
        cleaned_data["sort_order"] = cleaned_data.get("sort_order") or 0
        cleaned_data["unit_cost"] = cleaned_data.get("unit_cost") or Decimal("0")
        cleaned_data["discount_value"] = (
            cleaned_data.get("discount_value") or Decimal("0")
        )
        prod = cleaned_data.get("product")
        var = cleaned_data.get("product_variant")
        if var and prod and var.product_id != prod.pk:
            raise ValidationError(
                {"product_variant": "The option must belong to the selected product."}
            )
        if var and not prod:
            cleaned_data["product"] = var.product
        quantity = cleaned_data.get("quantity")
        unit_price = cleaned_data.get("unit_price")
        unit_cost = cleaned_data.get("unit_cost")
        discount_value = cleaned_data.get("discount_value")
        discount_type = cleaned_data.get("discount_type")
        tax_rate = cleaned_data.get("tax_rate")
        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        if unit_price is not None and unit_price < 0:
            self.add_error("unit_price", "Unit price cannot be negative.")
        if unit_cost is not None and unit_cost < 0:
            self.add_error("unit_cost", "Unit cost cannot be negative.")
        if discount_value is not None and discount_value < 0:
            self.add_error("discount_value", "Discount cannot be negative.")
        if (
            discount_type == CommercialDocument.DISCOUNT_PERCENT
            and discount_value is not None
            and discount_value > 100
        ):
            self.add_error("discount_value", "Percentage discount cannot exceed 100%.")
        if tax_rate is not None and not 0 <= tax_rate <= 100:
            self.add_error("tax_rate", "Tax rate must be between 0 and 100.")
        source_type = cleaned_data.get("source_type")
        if source_type in (
            CommercialLine.SOURCE_EXTERNAL,
            CommercialLine.SOURCE_CONSIGNMENT,
        ) and not (cleaned_data.get("supplier_name") or "").strip():
            self.add_error(
                "supplier_name",
                "Record the supplier or owner for external and consignment items.",
            )
        if prod and source_type == CommercialLine.SOURCE_CUSTOM:
            cleaned_data["source_type"] = (
                CommercialLine.SOURCE_SERVICE
                if prod.kind == Product.KIND_SERVICE
                else CommercialLine.SOURCE_STOCK
            )
        return cleaned_data


class RequiredCommercialLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_lines = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
        ]
        if not active_lines:
            raise ValidationError("Add at least one line item.")


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


class PaymentRefundForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference"].required = True
        self.fields["reference"].help_text = (
            "Required: unique refund adjustment reference for this payment."
        )

    def clean_reference(self):
        reference = (self.cleaned_data.get("reference") or "").strip()
        if not reference:
            raise forms.ValidationError(
                "Enter the reference for this refund adjustment."
            )
        return reference

    class Meta:
        model = PaymentRefund
        fields = ("amount", "reason", "reference")
        widgets = {
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
        }


class AccountPaymentForm(forms.ModelForm):
    class Meta:
        model = AccountPayment
        fields = (
            "customer",
            "customer_name",
            "amount",
            "method",
            "reference",
            "note",
        )
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "customer_name": forms.TextInput(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01"}
            ),
            "method": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        name = (cleaned.get("customer_name") or "").strip()
        if customer and not name:
            cleaned["customer_name"] = customer.name
        elif not customer and not name:
            self.add_error("customer_name", "Enter or select a customer.")
        return cleaned


class DocumentActionForm(forms.Form):
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
