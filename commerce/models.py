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
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
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
