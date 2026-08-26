from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class StockAdjustment(models.Model):
    """Manual stock adjustment done by staff (for corrections, stock counts, damages)."""

    REASON_COUNT = "count"
    REASON_DAMAGE = "damage"
    REASON_RETURN = "return"
    REASON_CORRECTION = "correction"
    REASON_JOB = "job"
    REASON_OTHER = "other"
    REASON_CHOICES = [
        (REASON_COUNT, "Stock count"),
        (REASON_DAMAGE, "Damage / write-off"),
        (REASON_RETURN, "Return"),
        (REASON_CORRECTION, "Correction"),
        (REASON_JOB, "Job / repair (parts)"),
        (REASON_OTHER, "Other"),
    ]

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="stock_adjustments"
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_adjustments",
    )
    quantity_delta = models.IntegerField(help_text="Positive or negative.")
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default=REASON_OTHER)
    note = models.CharField(max_length=255, blank=True)
    job = models.ForeignKey(
        "operations.JobCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_adjustments",
        help_text="When set, this movement is tied to a repair job (typically parts consumption).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        bits = []
        if self.job_id:
            bits.append(f"job {self.job.number}")
        if self.product_variant_id:
            bits.append(str(self.product_variant))
        else:
            bits.append(str(self.product))
        bits.append(f"{self.quantity_delta:+d}")
        return " · ".join(bits)

    def clean(self) -> None:
        super().clean()
        if (
            self.product_variant_id
            and self.product_id
            and self.product_variant.product_id != self.product_id
        ):
            raise ValidationError("The variant must belong to the selected product.")

    @transaction.atomic
    def apply(self) -> None:
        from catalog.models import Product, ProductVariant

        delta = int(self.quantity_delta)
        if self.product_variant_id:
            qs = ProductVariant.objects.select_for_update().filter(
                pk=self.product_variant_id
            )
        else:
            qs = Product.objects.select_for_update().filter(pk=self.product_id)
        if delta < 0:
            qs = qs.filter(stock_quantity__gte=-delta)
        updated = qs.update(stock_quantity=models.F("stock_quantity") + delta)
        if updated != 1:
            raise ValidationError("This adjustment would make stock negative.")
        from inventory.services import record_stock_movement

        record_stock_movement(
            product=self.product,
            product_variant=self.product_variant,
            quantity_delta=delta,
            movement_type=StockMovement.TYPE_ADJUSTMENT,
            reference=f"ADJ-{self.pk}",
            note=self.note or self.get_reason_display(),
            actor=self.created_by,
            adjustment=self,
        )


class StockMovement(models.Model):
    TYPE_SALE = "sale"
    TYPE_PURCHASE = "purchase"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_CUSTOMER_RETURN = "customer_return"
    TYPE_SUPPLIER_RETURN = "supplier_return"
    TYPE_CANCELLATION = "cancellation"
    TYPE_CHOICES = [
        (TYPE_SALE, "Sale"),
        (TYPE_PURCHASE, "Purchase receipt"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_CUSTOMER_RETURN, "Customer return"),
        (TYPE_SUPPLIER_RETURN, "Supplier return"),
        (TYPE_CANCELLATION, "Order cancellation"),
    ]

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="stock_movements"
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    quantity_delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    movement_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    reference = models.CharField(max_length=64, blank=True, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements_recorded",
    )
    adjustment = models.OneToOneField(
        StockAdjustment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.reference or self.get_movement_type_display()} {self.quantity_delta:+d}"


class StockTake(models.Model):
    """A stock take / cycle count session covering one or more products."""

    STATUS_OPEN = "open"
    STATUS_POSTED = "posted"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_OPEN, "In progress"),
        (STATUS_POSTED, "Posted"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    reference = models.CharField(max_length=24, unique=True, blank=True)
    name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional label, e.g. 'June cycle count — laptops'.",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_takes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.reference or 'STK'} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            today = timezone.localdate().strftime("%Y%m%d")
            base = f"STK-{today}"
            existing = StockTake.objects.filter(reference__startswith=base).count()
            self.reference = f"{base}-{existing + 1:03d}"
        super().save(*args, **kwargs)

    @property
    def is_open(self) -> bool:
        return self.status == self.STATUS_OPEN

    @transaction.atomic
    def post(self, actor=None) -> int:
        """Apply each line as a counted vs system delta. Returns line count posted."""
        if self.status != self.STATUS_OPEN:
            return 0
        posted = 0
        for line in self.lines.select_for_update().all():
            delta = line.counted_quantity - line.system_quantity
            if delta != 0:
                adj = StockAdjustment(
                    product=line.product,
                    product_variant=line.product_variant,
                    quantity_delta=delta,
                    reason=StockAdjustment.REASON_COUNT,
                    note=f"Stock take {self.reference} (line {line.pk})",
                    created_by=actor,
                )
                adj.save()
                adj.apply()
            posted += 1
        self.status = self.STATUS_POSTED
        self.posted_at = timezone.now()
        self.save(update_fields=["status", "posted_at"])
        return posted


class StockTakeLine(models.Model):
    take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_take_lines",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_take_lines",
    )
    system_quantity = models.IntegerField(
        default=0, help_text="Snapshot of on-hand when the line was added."
    )
    counted_quantity = models.PositiveIntegerField(
        default=0, help_text="Actual count from the floor."
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["product__name", "id"]

    def __str__(self) -> str:
        return f"{self.product.name} count={self.counted_quantity}"

    @property
    def variance(self) -> int:
        return int(self.counted_quantity) - int(self.system_quantity)


# Imported here so Django registers the cross-device workflow models.
from inventory.product_photo_models import ProductPhotoSession, StaffPushSubscription  # noqa: E402,F401
