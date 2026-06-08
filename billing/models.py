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
    TYPE_QUOTE = "quote"
    TYPE_PROFORMA = "proforma"
    TYPE_INVOICE = "invoice"
    TYPE_RECEIPT = "receipt"
    TYPE_DELIVERY_NOTE = "delivery_note"
    TYPE_DEMAND_NOTE = "demand_note"
    TYPE_CHOICES = [
        (TYPE_QUOTE, "Quotation"),
        (TYPE_PROFORMA, "Proforma invoice"),
        (TYPE_INVOICE, "Tax invoice"),
        (TYPE_RECEIPT, "Receipt"),
        (TYPE_DELIVERY_NOTE, "Delivery note"),
        (TYPE_DEMAND_NOTE, "Demand note"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_PARTIALLY_PAID = "partial"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PARTIALLY_PAID, "Partially paid"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PREFIX = {
        TYPE_QUOTE: "QUO",
        TYPE_PROFORMA: "PRO",
        TYPE_INVOICE: "INV",
        TYPE_RECEIPT: "REC",
        TYPE_DELIVERY_NOTE: "DN",
        TYPE_DEMAND_NOTE: "DEM",
    }

    doc_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    number = models.CharField(max_length=32, unique=True, db_index=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="documents"
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    title = models.CharField(max_length=200, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
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

    class Meta:
        ordering = ["-issue_date", "-id"]

    def __str__(self) -> str:
        return f"{self.number} ({self.get_doc_type_display()})"

    def ensure_customer_quote_token(self) -> None:
        if self.quote_customer_token is None:
            self.quote_customer_token = uuid.uuid4()

    @property
    def customer_quote_pending(self) -> bool:
        return (
            self.doc_type == self.TYPE_QUOTE
            and self.quote_requires_customer_acceptance
            and self.quote_customer_accepted is None
        )

    def recalculate_from_lines(self) -> None:
        sub = sum(
            (line.line_total for line in self.lines.all()),
            Decimal("0"),
        )
        self.subtotal = sub.quantize(Decimal("0.01"))
        self.tax_amount = (
            self.subtotal * (self.tax_rate / Decimal("100"))
        ).quantize(Decimal("0.01"))
        self.total = (self.subtotal + self.tax_amount).quantize(Decimal("0.01"))

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
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

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
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class DocumentPayment(models.Model):
    METHOD_CASH = "cash"
    METHOD_CARD = "card"
    METHOD_TRANSFER = "transfer"
    METHOD_OTHER = "other"
    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_CARD, "Card"),
        (METHOD_TRANSFER, "Bank transfer"),
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
