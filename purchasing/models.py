from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from billing.models import allocate_document_number
from catalog.models import Product, ProductVariant


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PurchaseOrder(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_PARTIAL = "partial"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent to supplier"),
        (STATUS_PARTIAL, "Partially received"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    number = models.CharField(max_length=32, unique=True, db_index=True, blank=True, default="")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    ordered_on = models.DateField(default=timezone.localdate)
    expected_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_on", "-id"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = allocate_document_number("PO")
        super().save(*args, **kwargs)

    @property
    def total_ordered_value(self) -> Decimal:
        return sum((l.line_total for l in self.lines.all()), Decimal("0")).quantize(Decimal("0.01"))

    @property
    def total_received_value(self) -> Decimal:
        return sum((l.received_total for l in self.lines.all()), Decimal("0")).quantize(Decimal("0.01"))

    def sync_receiving_status(self) -> None:
        if self.status == self.STATUS_CANCELLED:
            return
        lines = list(self.lines.all())
        if not lines:
            return
        all_received = all(l.received_quantity >= l.quantity for l in lines)
        any_received = any(l.received_quantity > 0 for l in lines)
        if all_received:
            self.status = self.STATUS_RECEIVED
        elif any_received:
            self.status = self.STATUS_PARTIAL


class PurchaseLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_lines")
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_lines",
    )
    description = models.CharField(max_length=300, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    received_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.product.name}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if self.product_variant_id and self.product_id:
            if self.product_variant.product_id != self.product_id:
                raise ValidationError("The variant must belong to the selected product.")

    @property
    def line_total(self) -> Decimal:
        return (Decimal(self.quantity) * self.unit_cost).quantize(Decimal("0.01"))

    @property
    def received_total(self) -> Decimal:
        return (Decimal(self.received_quantity) * self.unit_cost).quantize(Decimal("0.01"))


class StockReceipt(models.Model):
    """A receiving event (GRN) that increments product stock quantities."""

    number = models.CharField(max_length=32, unique=True, db_index=True, blank=True, default="")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    received_on = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_receipts_recorded",
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-received_on", "-id"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = allocate_document_number("GRN")
        super().save(*args, **kwargs)


class StockReceiptLine(models.Model):
    receipt = models.ForeignKey(StockReceipt, on_delete=models.CASCADE, related_name="lines")
    purchase_line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity_received = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]

    @transaction.atomic
    def apply(self) -> None:
        """Apply this line: update PO line received qty and product stock."""
        pl = PurchaseLine.objects.select_for_update().get(pk=self.purchase_line_id)
        qty = int(self.quantity_received)
        if qty <= 0:
            return
        pl.received_quantity = int(pl.received_quantity) + qty
        pl.save(update_fields=["received_quantity"])
        if pl.product_variant_id:
            ProductVariant.objects.filter(pk=pl.product_variant_id).update(
                stock_quantity=models.F("stock_quantity") + qty
            )
        else:
            Product.objects.filter(pk=pl.product_id).update(
                stock_quantity=models.F("stock_quantity") + qty
            )
