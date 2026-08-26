from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Avg, Count, Min
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="subcategories",
        null=True,
        blank=True,
        help_text="Leave blank for a main menu category.",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, max_length=140)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        if self.parent_id:
            return f"{self.parent.name} — {self.name}"
        return self.name

    @property
    def is_main_category(self) -> bool:
        return self.parent_id is None

    def save(self, *args, **kwargs):
        if not self.slug:
            if self.parent_id:
                base = slugify(f"{self.parent.slug}-{self.name}")[:130]
            else:
                base = slugify(self.name)[:130]
            base = base or "category"
            candidate = base
            suffix = 1
            while Category.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                suffix_text = f"-{suffix}"
                candidate = f"{base[: 140 - len(suffix_text)]}{suffix_text}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class Product(models.Model):
    KIND_PHYSICAL = "physical"
    KIND_SERVICE = "service"
    KIND_CHOICES = [
        (KIND_PHYSICAL, "Hardware / product"),
        (KIND_SERVICE, "IT service"),
    ]

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_PHYSICAL)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=220)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    track_inventory = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(
        default=0,
        help_text="Alert when on-hand stock is at or below this level (0 = no alert).",
    )
    service_duration_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="For services — estimated hours.",
    )
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stock_quantity__gte=0),
                name="product_stock_nonnegative",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:200]
            self.slug = base
            n = 1
            while Product.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{n}"
                n += 1
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("product_detail", kwargs={"slug": self.slug})

    @property
    def is_low_stock(self) -> bool:
        if self.kind != self.KIND_PHYSICAL or not self.track_inventory:
            return False
        if self.reorder_level <= 0:
            return False
        if self.has_sellable_variants():
            tracked = self.variants.filter(is_active=True, track_inventory=True)
            if not tracked.exists():
                return False
            return any(int(v.stock_quantity) <= self.reorder_level for v in tracked)
        return int(self.stock_quantity) <= self.reorder_level

    @property
    def available_to_sell(self) -> bool:
        if self.kind == self.KIND_SERVICE:
            return True
        if self.kind == self.KIND_PHYSICAL and self.has_sellable_variants():
            return any(
                v.available_to_sell
                for v in self.variants.filter(is_active=True)
            )
        if not self.track_inventory:
            return True
        return self.stock_quantity > 0

    def decrement_stock(self, qty: int) -> None:
        if self.kind != self.KIND_PHYSICAL or not self.track_inventory:
            return
        new_qty = max(0, int(self.stock_quantity) - int(qty))
        Product.objects.filter(pk=self.pk).update(stock_quantity=new_qty)
        self.stock_quantity = new_qty

    def has_sellable_variants(self) -> bool:
        return self.variants.filter(is_active=True).exists()

    @property
    def primary_display_image(self):
        """Explicit main image, falling back to the first gallery image."""
        if self.image:
            return self.image
        img = (
            self.gallery_images.filter(image__isnull=False)
            .exclude(image="")
            .order_by("sort_order", "id")
            .first()
        )
        return img.image if img and img.image else None

    @property
    def min_active_variant_price(self) -> Decimal | None:
        v = self.variants.filter(is_active=True).aggregate(m=Min("price"))
        m = v["m"]
        return m if m is not None else None

    @property
    def active_variant_count(self) -> int:
        return self.variants.filter(is_active=True).count()

    @property
    def variants_total_stock(self) -> int | None:
        """Sum of on-hand units for active variants that track inventory, or None if none do."""
        tracked = [
            v
            for v in self.variants.filter(is_active=True)
            if v.track_inventory
        ]
        if not tracked:
            return None
        return sum(int(v.stock_quantity) for v in tracked)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="gallery_images"
    )
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    alt_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.product.name} image {self.pk}"


class ProductVariant(models.Model):
    """Optional SKU/price/stock breakdown (e.g. size, colour) for a product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    name = models.CharField(max_length=120, help_text="Shown to customers, e.g. 16GB / Silver.")
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    track_inventory = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stock_quantity__gte=0),
                name="variant_stock_nonnegative",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.name} — {self.name}"

    @property
    def available_to_sell(self) -> bool:
        if not self.is_active:
            return False
        if self.product.kind != Product.KIND_PHYSICAL:
            return True
        if not self.track_inventory:
            return True
        return self.stock_quantity > 0

    def decrement_stock(self, qty: int) -> None:
        if self.product.kind != Product.KIND_PHYSICAL or not self.track_inventory:
            return
        new_qty = max(0, int(self.stock_quantity) - int(qty))
        ProductVariant.objects.filter(pk=self.pk).update(stock_quantity=new_qty)
        self.stock_quantity = new_qty


class ProductReview(models.Model):
    RATING_CHOICES = [(i, f"{i} star{'s' if i != 1 else ''}") for i in range(1, 6)]

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_reviews",
    )
    author_name = models.CharField(max_length=120, blank=True)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, default=5)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_reviews",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.product.name} — {self.rating}★"

    @property
    def display_name(self) -> str:
        if self.author_name:
            return self.author_name
        if self.customer:
            return self.customer.name
        return "Customer"


class ProductSerial(models.Model):
    """An individually-tracked unit of a serialized product (e.g. laptop with serial number)."""

    STATUS_AVAILABLE = "available"
    STATUS_SOLD = "sold"
    STATUS_RMA = "rma"
    STATUS_WRITTEN_OFF = "written_off"
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "In stock"),
        (STATUS_SOLD, "Sold"),
        (STATUS_RMA, "Under RMA / warranty"),
        (STATUS_WRITTEN_OFF, "Written off"),
    ]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="serials"
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="serials",
    )
    serial_number = models.CharField(max_length=120)
    imei = models.CharField(max_length=64, blank=True)
    mac_address = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_AVAILABLE
    )
    sold_to = models.ForeignKey(
        "crm.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchased_serials",
    )
    sold_at = models.DateField(null=True, blank=True)
    warranty_months = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "serial_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "serial_number"],
                name="serial_unique_per_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.name} · SN {self.serial_number}"

    @property
    def warranty_expires_on(self):
        from datetime import date
        y = None
        if not self.sold_at or not self.warranty_months:
            return None
        y = self.sold_at.year + (self.sold_at.month - 1 + self.warranty_months) // 12
        m = (self.sold_at.month - 1 + self.warranty_months) % 12 + 1
        d = min(self.sold_at.day, 28)
        return date(y, m, d)

    @property
    def is_under_warranty(self) -> bool:
        from datetime import date
        exp = self.warranty_expires_on
        return exp is not None and exp >= date.today()


class WishlistItem(models.Model):
    """A product saved by a portal customer for later."""

    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlist_entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product"],
                name="wishlist_unique_customer_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.customer.name} ♥ {self.product.name}"


def product_review_summary(product) -> dict:
    """Aggregate rating stats for published reviews."""
    qs = product.reviews.filter(is_published=True)
    agg = qs.aggregate(avg=Avg("rating"), count=Count("id"))
    return {
        "avg": round(float(agg["avg"]), 1) if agg["avg"] is not None else None,
        "count": agg["count"] or 0,
    }
