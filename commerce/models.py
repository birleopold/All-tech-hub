import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, ProductVariant
from crm.models import Customer


class Coupon(models.Model):
    """Discount code applied at the cart/checkout level."""

    KIND_PERCENT = "percent"
    KIND_FIXED = "fixed"
    KIND_CHOICES = [
        (KIND_PERCENT, "Percent off"),
        (KIND_FIXED, "Fixed amount off"),
    ]

    code = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_PERCENT)
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Percent (0–100) for percent kind, or money amount for fixed kind.",
    )
    min_subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Cart subtotal must reach this amount before discount applies.",
    )
    max_uses = models.PositiveIntegerField(
        default=0, help_text="0 = unlimited uses."
    )
    times_used = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)
    active_from = models.DateTimeField(null=True, blank=True)
    active_until = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.active_from and now < self.active_from:
            return False
        if self.active_until and now > self.active_until:
            return False
        if self.max_uses and self.times_used >= self.max_uses:
            return False
        return True

    def compute_discount(self, subtotal: Decimal) -> Decimal:
        if subtotal < self.min_subtotal:
            return Decimal("0")
        if self.kind == self.KIND_PERCENT:
            pct = max(Decimal("0"), min(Decimal("100"), self.value))
            return (subtotal * pct / Decimal("100")).quantize(Decimal("0.01"))
        amount = max(Decimal("0"), self.value)
        return min(amount, subtotal).quantize(Decimal("0.01"))


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_DISPATCHED = "dispatched"
    STATUS_DELIVERED = "delivered"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready for pickup / dispatch"),
        (STATUS_DISPATCHED, "Dispatched"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    FULFILLMENT_DELIVERY = "delivery"
    FULFILLMENT_PICKUP = "pickup"
    FULFILLMENT_CHOICES = [
        (FULFILLMENT_DELIVERY, "Delivery"),
        (FULFILLMENT_PICKUP, "Pickup"),
    ]

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    view_key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Secret fragment for the public order receipt URL (not guessable from the reference).",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shop_orders",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    contact_name = models.CharField(max_length=200)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=64, blank=True)
    billing_summary = models.TextField(blank=True)
    shipping_summary = models.TextField(blank=True)
    fulfillment_type = models.CharField(
        max_length=16,
        choices=FULFILLMENT_CHOICES,
        default=FULFILLMENT_DELIVERY,
    )
    delivery_zone_name = models.CharField(max_length=140, blank=True)
    delivery_fee = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    customer_note = models.TextField(blank=True)
    staff_note = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    coupon_code_applied = models.CharField(max_length=40, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cancellation_reason = models.CharField(max_length=255, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-placed_at"]

    def __str__(self) -> str:
        return self.reference

    def get_absolute_url(self) -> str:
        return reverse(
            "order_detail",
            kwargs={"reference": self.reference, "view_key": self.view_key},
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.STATUS_CANCELLED,
            self.STATUS_DELIVERED,
            self.STATUS_FULFILLED,
        }


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, related_name="order_lines"
    )
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
    )
    description = models.CharField(max_length=300)
    sku = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.description}"

    @property
    def line_total(self) -> Decimal:
        return (Decimal(self.quantity) * self.unit_price).quantize(Decimal("0.01"))


class CustomerReturn(models.Model):
    DISPOSITION_RESTOCK = "restock"
    DISPOSITION_DAMAGED = "damaged"
    DISPOSITION_CHOICES = [
        (DISPOSITION_RESTOCK, "Return to stock"),
        (DISPOSITION_DAMAGED, "Damaged / do not restock"),
    ]

    reference = models.CharField(max_length=32, unique=True, db_index=True)
    order_line = models.ForeignKey(
        OrderLine, on_delete=models.PROTECT, related_name="returns"
    )
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    disposition = models.CharField(
        max_length=16, choices=DISPOSITION_CHOICES, default=DISPOSITION_RESTOCK
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="customer_returns_processed",
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-processed_at", "-id"]

    @property
    def previously_returned(self) -> int:
        return sum(
            self.order_line.returns.exclude(pk=self.pk).values_list(
                "quantity", flat=True
            )
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.quantity <= 0:
            raise ValidationError("Return quantity must be positive.")
        if self.previously_returned + self.quantity > self.order_line.quantity:
            raise ValidationError("Return quantity exceeds the quantity sold.")

    def __str__(self):
        return self.reference


class OrderStatusEvent(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_events"
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    visible_to_customer = models.BooleanField(default=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Shipment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_DELIVERED = "delivered"
    STATUS_EXCEPTION = "exception"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_IN_TRANSIT, "In transit"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_EXCEPTION, "Delivery exception"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")
    carrier = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    tracking_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class OrderStockRestoration(models.Model):
    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="stock_restoration"
    )
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_stock_restorations",
    )
    restored_at = models.DateTimeField(auto_now_add=True)
