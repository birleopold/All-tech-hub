import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from commerce.models import Order
from crm.models import Customer


class DocumentSequence(models.Model):
    """Per-prefix, per-year counters (QUO, PRO, INV, JC)."""

    key = models.CharField(max_length=8, db_index=True)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "year"], name="unique_doc_seq_year")
        ]

    def __str__(self) -> str:
        return f"{self.key}-{self.year}: {self.last_value}"


def allocate_document_number(key: str) -> str:
    year = timezone.now().year
    with transaction.atomic():
        row = (
            DocumentSequence.objects.select_for_update()
            .filter(key=key, year=year)
            .first()
        )
        if row is None:
            row = DocumentSequence.objects.create(key=key, year=year, last_value=0)
        row.last_value += 1
        row.save(update_fields=["last_value"])
        return f"{key}-{year}-{row.last_value:05d}"


class CommercialDocument(models.Model):
    PRICING_EXCLUSIVE = "exclusive"
    PRICING_INCLUSIVE = "inclusive"
    PRICING_CHOICES = [
        (PRICING_EXCLUSIVE, "Tax exclusive"),
        (PRICING_INCLUSIVE, "Tax inclusive"),
    ]
    DISCOUNT_PERCENT = "percent"
    DISCOUNT_FIXED = "fixed"
    DISCOUNT_CHOICES = [
        (DISCOUNT_PERCENT, "Percentage"),
        (DISCOUNT_FIXED, "Fixed amount"),
    ]
    TYPE_QUOTE = "quote"
    TYPE_PROFORMA = "proforma"
    TYPE_INVOICE = "invoice"
    TYPE_RECEIPT = "receipt"
    TYPE_DELIVERY_NOTE = "delivery_note"
    TYPE_DEMAND_NOTE = "demand_note"
    TYPE_CREDIT_NOTE = "credit_note"
    TYPE_CHOICES = [
        (TYPE_QUOTE, "Quotation"),
        (TYPE_PROFORMA, "Proforma invoice"),
        (TYPE_INVOICE, "Tax invoice"),
        (TYPE_RECEIPT, "Receipt"),
        (TYPE_DELIVERY_NOTE, "Delivery note"),
        (TYPE_DEMAND_NOTE, "Demand note"),
        (TYPE_CREDIT_NOTE, "Credit note"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_PARTIALLY_PAID = "partial"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PARTIALLY_PAID, "Partially paid"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    PREFIX = {
        TYPE_QUOTE: "QUO",
        TYPE_PROFORMA: "PRO",
        TYPE_INVOICE: "INV",
        TYPE_RECEIPT: "REC",
        TYPE_DELIVERY_NOTE: "DN",
        TYPE_DEMAND_NOTE: "DEM",
        TYPE_CREDIT_NOTE: "CRN",
    }

    doc_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    number = models.CharField(max_length=32, unique=True, db_index=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Customer name as printed on this document.",
    )
    customer_company = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=64, blank=True)
    customer_tax_reference = models.CharField(max_length=120, blank=True)
    customer_address = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    title = models.CharField(max_length=200, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    pricing_mode = models.CharField(
        max_length=12, choices=PRICING_CHOICES, default=PRICING_EXCLUSIVE
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    line_discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    discount_type = models.CharField(
        max_length=12, choices=DISCOUNT_CHOICES, default=DISCOUNT_PERCENT
    )
    discount_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    shipping_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    other_charges = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    other_charges_label = models.CharField(max_length=120, blank=True)
    withholding_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )
    withholding_tax_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    tax_exempt = models.BooleanField(default=False)
    tax_exemption_reason = models.CharField(max_length=255, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    amount_tendered = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    receipt_payment_method = models.CharField(
        max_length=20,
        choices=[
            ("cash", "Cash"),
            ("card", "Card"),
            ("transfer", "Bank transfer"),
            ("mobile_money", "Mobile Money"),
            ("cheque", "Cheque"),
            ("other", "Other"),
        ],
        blank=True,
    )
    receipt_payment_reference = models.CharField(max_length=120, blank=True)
    change_due = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    hide_prices = models.BooleanField(
        default=False, help_text="Useful for delivery notes and packing copies."
    )
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_documents_sold",
    )
    location = models.CharField(max_length=160, blank=True)
    vehicle_reference = models.CharField(
        max_length=120, blank=True, help_text="Registration, fleet number, or vehicle."
    )
    contact_reference = models.CharField(max_length=160, blank=True)
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    source_document = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_documents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_authored",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_documents_locked",
    )
    revision_number = models.PositiveIntegerField(default=0)
    cancellation_reason = models.CharField(max_length=500, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_documents_cancelled",
    )
    inventory_posted_at = models.DateTimeField(null=True, blank=True)
    quote_requires_internal_approval = models.BooleanField(
        default=False,
        help_text="If set, staff must approve this quotation before converting to proforma or invoice.",
    )
    quote_internally_approved = models.BooleanField(default=False)
    quote_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes_internally_approved",
    )
    quote_approved_at = models.DateTimeField(null=True, blank=True)
    quote_requires_customer_acceptance = models.BooleanField(
        default=False,
        help_text="Customer must accept via the secure link before converting this quote.",
    )
    quote_customer_token = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
        db_index=True,
    )
    quote_customer_accepted = models.BooleanField(
        null=True,
        blank=True,
        help_text="Null = awaiting response, True = accepted, False = declined.",
    )
    quote_customer_responded_at = models.DateTimeField(null=True, blank=True)
    quote_customer_signature_name = models.CharField(max_length=200, blank=True)
    quote_customer_decline_reason = models.CharField(max_length=500, blank=True)
    last_payment_reminder_sent = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time an automated due-date reminder email was sent for this document.",
    )
    payment_request_token = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Secure public payment request link for invoices and proformas.",
    )

    class Meta:
        ordering = ["-issue_date", "-id"]
        permissions = [
            ("override_document_discount", "Can override document discount limits"),
            ("override_document_tax", "Can override document tax"),
            ("view_document_margin", "Can view document costs and margins"),
            ("revise_issued_document", "Can revise issued documents"),
            ("void_commercial_document", "Can void commercial documents"),
            ("approve_high_value_document", "Can approve high-value documents"),
        ]

    def __str__(self) -> str:
        return f"{self.number} ({self.get_doc_type_display()})"

    def capture_customer_snapshot(self, overwrite: bool = False) -> None:
        """Copy linked CRM details onto the document without requiring an account."""
        if not self.customer_id:
            return
        customer = self.customer
        values = {
            "customer_name": customer.name,
            "customer_company": customer.company_name,
            "customer_email": customer.email,
            "customer_phone": customer.phone,
            "customer_tax_reference": customer.tax_reference,
        }
        for field, value in values.items():
            if overwrite or not getattr(self, field):
                setattr(self, field, value or "")

    def customer_snapshot_kwargs(self) -> dict:
        return {
            "customer": self.customer,
            "customer_name": self.display_customer_name,
            "customer_company": self.display_customer_company,
            "customer_email": self.display_customer_email,
            "customer_phone": self.display_customer_phone,
            "customer_tax_reference": self.display_customer_tax_reference,
            "customer_address": self.customer_address,
        }

    def save(self, *args, **kwargs) -> None:
        self.capture_customer_snapshot()
        super().save(*args, **kwargs)

    @property
    def display_customer_name(self) -> str:
        return self.customer_name or (
            self.customer.name if self.customer_id else "Walk-in customer"
        )

    @property
    def display_customer_company(self) -> str:
        return self.customer_company or (
            self.customer.company_name if self.customer_id else ""
        )

    @property
    def display_customer_email(self) -> str:
        return self.customer_email or (
            self.customer.email if self.customer_id else ""
        )

    @property
    def display_customer_phone(self) -> str:
        return self.customer_phone or (
            self.customer.phone if self.customer_id else ""
        )

    @property
    def display_customer_tax_reference(self) -> str:
        return self.customer_tax_reference or (
            self.customer.tax_reference if self.customer_id else ""
        )

    def ensure_customer_quote_token(self) -> None:
        if self.quote_customer_token is None:
            self.quote_customer_token = uuid.uuid4()

    def ensure_payment_request_token(self) -> None:
        if self.payment_request_token is None:
            self.payment_request_token = uuid.uuid4()

    @property
    def supports_payment_request(self) -> bool:
        return self.doc_type in (self.TYPE_INVOICE, self.TYPE_PROFORMA)

    @property
    def customer_quote_pending(self) -> bool:
        return (
            self.doc_type == self.TYPE_QUOTE
            and self.quote_requires_customer_acceptance
            and self.quote_customer_accepted is None
        )

    def recalculate_from_lines(self) -> None:
        lines = list(self.lines.all())
        line_subtotal = sum((line.net_subtotal for line in lines), Decimal("0"))
        self.line_discount_amount = sum(
            (line.discount_amount_calculated for line in lines), Decimal("0")
        ).quantize(Decimal("0.01"))
        self.subtotal = line_subtotal.quantize(Decimal("0.01"))
        if self.discount_type == self.DISCOUNT_PERCENT:
            rate = min(max(self.discount_value, Decimal("0")), Decimal("100"))
            doc_discount = self.subtotal * rate / Decimal("100")
        else:
            doc_discount = min(max(self.discount_value, Decimal("0")), self.subtotal)
        self.discount_amount = doc_discount.quantize(Decimal("0.01"))

        discounted_ratio = (
            (self.subtotal - self.discount_amount) / self.subtotal
            if self.subtotal > 0
            else Decimal("0")
        )
        line_tax = sum((line.tax_amount_calculated for line in lines), Decimal("0"))
        charges = max(self.shipping_amount, Decimal("0")) + max(
            self.other_charges, Decimal("0")
        )
        if self.tax_exempt:
            tax = Decimal("0")
        else:
            tax = line_tax * discounted_ratio
            if self.pricing_mode == self.PRICING_EXCLUSIVE:
                tax += charges * self.tax_rate / Decimal("100")
        self.tax_amount = tax.quantize(Decimal("0.01"))
        before_withholding = (
            self.subtotal - self.discount_amount + charges + self.tax_amount
        )
        self.withholding_tax_amount = (
            before_withholding
            * min(max(self.withholding_tax_rate, Decimal("0")), Decimal("100"))
            / Decimal("100")
        ).quantize(Decimal("0.01"))
        self.total = max(
            Decimal("0"), before_withholding - self.withholding_tax_amount
        ).quantize(Decimal("0.01"))
        if self.doc_type == self.TYPE_CREDIT_NOTE:
            self.subtotal = -abs(self.subtotal)
            self.line_discount_amount = -abs(self.line_discount_amount)
            self.discount_amount = -abs(self.discount_amount)
            self.tax_amount = -abs(self.tax_amount)
            self.withholding_tax_amount = -abs(self.withholding_tax_amount)
            self.total = -abs(self.total)
        self.change_due = max(
            Decimal("0"), self.amount_tendered - self.total
        ).quantize(Decimal("0.01"))

    @property
    def total_cost(self) -> Decimal:
        return sum((line.total_cost for line in self.lines.all()), Decimal("0")).quantize(
            Decimal("0.01")
        )

    @property
    def gross_profit(self) -> Decimal:
        return (self.subtotal - self.discount_amount - self.total_cost).quantize(
            Decimal("0.01")
        )

    @property
    def gross_margin_percent(self) -> Decimal:
        net_revenue = self.subtotal - self.discount_amount
        if net_revenue <= 0:
            return Decimal("0")
        return (self.gross_profit / net_revenue * Decimal("100")).quantize(
            Decimal("0.01")
        )

    @property
    def section_totals(self) -> list[dict]:
        totals: dict[str, Decimal] = {}
        for line in self.lines.all():
            label = line.section.strip() or "Unsectioned"
            totals[label] = totals.get(label, Decimal("0")) + line.line_total
        return [
            {"label": label, "total": total.quantize(Decimal("0.01"))}
            for label, total in totals.items()
            if label != "Unsectioned" or len(totals) > 1
        ]

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    def lock(self, actor=None) -> None:
        if self.locked_at is None:
            self.locked_at = timezone.now()
            self.locked_by = actor

    def snapshot_data(self) -> dict:
        return {
            "number": self.number,
            "doc_type": self.doc_type,
            "status": self.status,
            "customer": {
                "name": self.display_customer_name,
                "company": self.display_customer_company,
                "email": self.display_customer_email,
                "phone": self.display_customer_phone,
                "tax_reference": self.display_customer_tax_reference,
                "address": self.customer_address,
            },
            "issue_date": self.issue_date.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "pricing_mode": self.pricing_mode,
            "tax_rate": str(self.tax_rate),
            "subtotal": str(self.subtotal),
            "discount_amount": str(self.discount_amount),
            "tax_amount": str(self.tax_amount),
            "withholding_tax_amount": str(self.withholding_tax_amount),
            "shipping_amount": str(self.shipping_amount),
            "other_charges": str(self.other_charges),
            "total": str(self.total),
            "notes": self.notes,
            "terms": self.terms,
            "location": self.location,
            "vehicle_reference": self.vehicle_reference,
            "contact_reference": self.contact_reference,
            "lines": [
                line.snapshot_data() for line in self.lines.order_by("sort_order", "id")
            ],
        }

    @property
    def balance_due(self) -> Decimal:
        due = (self.total - self.amount_paid).quantize(Decimal("0.01"))
        return due if due > 0 else Decimal("0")

    def sync_payment_status(self) -> None:
        """Update status from amount_paid vs total (call after payments)."""
        if self.status == self.STATUS_CANCELLED:
            return
        paid = self.amount_paid.quantize(Decimal("0.01"))
        total = self.total.quantize(Decimal("0.01"))
        if paid <= 0:
            if self.status in (self.STATUS_PARTIALLY_PAID, self.STATUS_PAID):
                self.status = self.STATUS_ISSUED
        elif paid < total:
            self.status = self.STATUS_PARTIALLY_PAID
        else:
            self.status = self.STATUS_PAID


class CommercialLine(models.Model):
    SOURCE_STOCK = "stock"
    SOURCE_EXTERNAL = "external"
    SOURCE_CONSIGNMENT = "consignment"
    SOURCE_SERVICE = "service"
    SOURCE_CUSTOM = "custom"
    SOURCE_CHOICES = [
        (SOURCE_STOCK, "Own stock"),
        (SOURCE_EXTERNAL, "External purchase"),
        (SOURCE_CONSIGNMENT, "Consignment"),
        (SOURCE_SERVICE, "Service / labour"),
        (SOURCE_CUSTOM, "Custom / other"),
    ]
    document = models.ForeignKey(
        CommercialDocument, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_lines",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_lines",
    )
    description = models.CharField(max_length=400)
    source_type = models.CharField(
        max_length=16, choices=SOURCE_CHOICES, default=SOURCE_CUSTOM
    )
    sku = models.CharField(max_length=64, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    warranty = models.CharField(max_length=160, blank=True)
    line_note = models.CharField(max_length=255, blank=True)
    section = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    supplier_name = models.CharField(max_length=200, blank=True)
    source_reference = models.CharField(max_length=120, blank=True)
    discount_type = models.CharField(
        max_length=12,
        choices=CommercialDocument.DISCOUNT_CHOICES,
        default=CommercialDocument.DISCOUNT_PERCENT,
    )
    discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave blank to use the document tax rate.",
    )
    tax_exempt = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.description

    def clean(self) -> None:
        super().clean()
        if self.product_variant_id and self.product_id:
            if self.product_variant.product_id != self.product_id:
                raise ValidationError(
                    {
                        "product_variant": "The selected option must belong to the selected product."
                    }
                )

    def save(self, *args, **kwargs) -> None:
        if self.product_variant_id:
            self.product_id = self.product_variant.product_id
        super().save(*args, **kwargs)

    @property
    def gross_amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @property
    def discount_amount_calculated(self) -> Decimal:
        gross = self.gross_amount
        if self.discount_type == CommercialDocument.DISCOUNT_PERCENT:
            value = gross * min(
                max(self.discount_value, Decimal("0")), Decimal("100")
            ) / Decimal("100")
        else:
            value = min(max(self.discount_value, Decimal("0")), gross)
        return value.quantize(Decimal("0.01"))

    @property
    def effective_tax_rate(self) -> Decimal:
        if self.tax_exempt or self.document.tax_exempt:
            return Decimal("0")
        return self.tax_rate if self.tax_rate is not None else self.document.tax_rate

    @property
    def net_subtotal(self) -> Decimal:
        after_discount = self.gross_amount - self.discount_amount_calculated
        rate = self.effective_tax_rate
        if (
            self.document.pricing_mode == CommercialDocument.PRICING_INCLUSIVE
            and rate > 0
        ):
            return (
                after_discount / (Decimal("1") + rate / Decimal("100"))
            ).quantize(Decimal("0.01"))
        return after_discount.quantize(Decimal("0.01"))

    @property
    def tax_amount_calculated(self) -> Decimal:
        rate = self.effective_tax_rate
        if rate <= 0:
            return Decimal("0")
        if self.document.pricing_mode == CommercialDocument.PRICING_INCLUSIVE:
            return (self.gross_amount - self.discount_amount_calculated - self.net_subtotal).quantize(
                Decimal("0.01")
            )
        return (self.net_subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def line_total(self) -> Decimal:
        return (self.net_subtotal + self.tax_amount_calculated).quantize(
            Decimal("0.01")
        )

    @property
    def total_cost(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"))

    @property
    def gross_profit(self) -> Decimal:
        return (self.net_subtotal - self.total_cost).quantize(Decimal("0.01"))

    def snapshot_data(self) -> dict:
        return {
            "description": self.description,
            "source_type": self.source_type,
            "sku": self.sku,
            "serial_number": self.serial_number,
            "warranty": self.warranty,
            "note": self.line_note,
            "section": self.section,
            "quantity": str(self.quantity),
            "unit_price": str(self.unit_price),
            "unit_cost": str(self.unit_cost),
            "discount_type": self.discount_type,
            "discount_value": str(self.discount_value),
            "tax_rate": str(self.tax_rate) if self.tax_rate is not None else None,
            "tax_exempt": self.tax_exempt,
            "supplier_name": self.supplier_name,
            "source_reference": self.source_reference,
            "total": str(self.line_total),
        }


class DocumentPayment(models.Model):
    METHOD_CASH = "cash"
    METHOD_CARD = "card"
    METHOD_TRANSFER = "transfer"
    METHOD_MOBILE_MONEY = "mobile_money"
    METHOD_CHEQUE = "cheque"
    METHOD_OTHER = "other"
    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_CARD, "Card"),
        (METHOD_TRANSFER, "Bank transfer"),
        (METHOD_MOBILE_MONEY, "Mobile Money"),
        (METHOD_CHEQUE, "Cheque"),
        (METHOD_OTHER, "Other"),
    ]

    document = models.ForeignKey(
        CommercialDocument,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_payments_reconciled",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="document_payments_recorded",
    )

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"{self.document.number} +{self.amount}"

    @property
    def refunded_amount(self) -> Decimal:
        return sum(
            self.refunds.values_list("amount", flat=True), Decimal("0")
        ).quantize(Decimal("0.01"))

    @property
    def refundable_amount(self) -> Decimal:
        return max(Decimal("0"), self.amount - self.refunded_amount)


class PaymentRefund(models.Model):
    payment = models.ForeignKey(
        DocumentPayment, on_delete=models.PROTECT, related_name="refunds"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    reference = models.CharField(max_length=120, blank=True)
    credit_note = models.ForeignKey(
        CommercialDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_refunds",
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payment_refunds_processed",
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-processed_at", "-id"]

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError("Refund amount must be positive.")
        if self.payment_id and self.amount > self.payment.refundable_amount:
            raise ValidationError("Refund exceeds the remaining refundable amount.")


class DocumentRevision(models.Model):
    document = models.ForeignKey(
        CommercialDocument, on_delete=models.CASCADE, related_name="revisions"
    )
    revision_number = models.PositiveIntegerField()
    reason = models.CharField(max_length=255, blank=True)
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_revisions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revision_number", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "revision_number"],
                name="unique_document_revision_number",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document.number} revision {self.revision_number}"


class DocumentTemplate(models.Model):
    name = models.CharField(max_length=160, unique=True)
    doc_type = models.CharField(
        max_length=16, choices=CommercialDocument.TYPE_CHOICES
    )
    title = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    pricing_mode = models.CharField(
        max_length=12,
        choices=CommercialDocument.PRICING_CHOICES,
        default=CommercialDocument.PRICING_EXCLUSIVE,
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )
    lines = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_templates_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CustomerCredit(models.Model):
    STATUS_OPEN = "open"
    STATUS_USED = "used"
    STATUS_VOID = "void"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Available"),
        (STATUS_USED, "Fully used"),
        (STATUS_VOID, "Void"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credits",
    )
    customer_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_OPEN
    )
    source_document = models.ForeignKey(
        CommercialDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_credits",
    )
    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_credits_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.customer_name}: {self.remaining_amount}"


class AccountPayment(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="account_payments",
    )
    customer_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=DocumentPayment.METHOD_CHOICES)
    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_payments_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]

    @property
    def allocated_amount(self) -> Decimal:
        return sum(
            self.allocations.values_list("amount", flat=True), Decimal("0")
        ).quantize(Decimal("0.01"))

    @property
    def unallocated_amount(self) -> Decimal:
        return max(Decimal("0"), self.amount - self.allocated_amount)


class PaymentAllocation(models.Model):
    account_payment = models.ForeignKey(
        AccountPayment, on_delete=models.CASCADE, related_name="allocations"
    )
    document = models.ForeignKey(
        CommercialDocument,
        on_delete=models.PROTECT,
        related_name="account_payment_allocations",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_allocations_created",
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["allocated_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account_payment", "document"],
                name="unique_account_payment_document_allocation",
            )
        ]

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError("Allocation amount must be positive.")
        if self.document.doc_type not in (
            CommercialDocument.TYPE_INVOICE,
            CommercialDocument.TYPE_PROFORMA,
        ):
            raise ValidationError("Payments can only be allocated to invoices or proformas.")
