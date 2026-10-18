from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from merchandising.constants import commercial_page_path


class ProductCommerceProfile(models.Model):
    """Customer-facing specifications and Merchant publication controls."""

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="commerce_profile",
    )
    processor_family = models.CharField(max_length=160, blank=True)
    processor_generation = models.CharField(max_length=80, blank=True)
    ram_capacity = models.CharField(max_length=80, blank=True)
    ram_type = models.CharField(max_length=80, blank=True)
    storage_capacity = models.CharField(max_length=80, blank=True)
    storage_type = models.CharField(max_length=80, blank=True)
    screen_size = models.CharField(max_length=80, blank=True)
    screen_resolution = models.CharField(max_length=120, blank=True)
    touchscreen = models.BooleanField(null=True, blank=True)
    graphics = models.CharField(max_length=180, blank=True)
    operating_system = models.CharField(max_length=120, blank=True)
    battery_health_note = models.CharField(max_length=220, blank=True)
    keyboard_condition = models.CharField(max_length=180, blank=True)
    charger_included = models.BooleanField(
        null=True,
        blank=True,
        help_text="Leave unknown until the exact charger or power adapter is checked.",
    )
    accessories_included = models.CharField(max_length=220, blank=True)
    warranty_months = models.PositiveIntegerField(default=0)
    condition_notes = models.TextField(blank=True)
    actual_photos = models.BooleanField(
        default=False,
        help_text="Confirm that the public gallery shows the actual unit or stock being sold.",
    )
    identity_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When brand, exact model and product identifiers were checked.",
    )
    condition_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When new, refurbished or used condition was physically confirmed.",
    )
    delivery_note = models.CharField(max_length=240, blank=True)
    stock_confirmed_at = models.DateTimeField(null=True, blank=True)
    price_verified_at = models.DateTimeField(null=True, blank=True)
    merchant_enabled = models.BooleanField(
        default=False,
        help_text="The product is intentionally approved for Merchant Center publication.",
    )
    merchant_shipping_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    merchant_free_shipping = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name"]
        verbose_name = "Product commercial profile"
        verbose_name_plural = "Product commercial profiles"

    def __str__(self) -> str:
        return f"Commercial profile — {self.product.name}"

    @property
    def specification_pairs(self) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        fields = (
            ("Processor", self.processor_family),
            ("Processor generation", self.processor_generation),
            ("RAM", self.ram_capacity),
            ("RAM type", self.ram_type),
            ("Storage", self.storage_capacity),
            ("Storage type", self.storage_type),
            ("Screen size", self.screen_size),
            ("Screen resolution", self.screen_resolution),
            ("Graphics", self.graphics),
            ("Operating system", self.operating_system),
            ("Battery", self.battery_health_note),
            ("Keyboard", self.keyboard_condition),
            ("Accessories included", self.accessories_included),
            ("Delivery", self.delivery_note),
        )
        values.extend((label, value) for label, value in fields if value)
        if self.touchscreen is not None:
            values.append(("Touchscreen", "Yes" if self.touchscreen else "No"))
        if self.charger_included is not None:
            values.append(
                ("Charger included", "Yes" if self.charger_included else "No")
            )
        if self.warranty_months:
            values.append(("Warranty", f"{self.warranty_months} month(s)"))
        return values

    def merchant_missing_fields(self) -> list[str]:
        from django.core.exceptions import ObjectDoesNotExist

        product = self.product
        missing: list[str] = []
        if not self.merchant_enabled:
            missing.append("merchant approval")
        if not product.is_published:
            missing.append("published status")
        if product.kind != product.KIND_PHYSICAL:
            missing.append("physical product type")
        if not product.primary_display_image:
            missing.append("product image")
        if not product.short_description and not product.description:
            missing.append("description")
        if product.price is None or product.price <= Decimal("0"):
            missing.append("valid price")
        try:
            metadata = product.growth_data
        except ObjectDoesNotExist:
            metadata = None
        brand = (getattr(metadata, "brand", "") or "").strip()
        gtin = (getattr(metadata, "gtin", "") or "").strip()
        mpn = (getattr(metadata, "mpn", "") or "").strip()
        condition = (getattr(metadata, "condition", "") or "").strip()
        if not brand:
            missing.append("brand")
        if not condition:
            missing.append("condition")
        if not gtin and not (brand and mpn):
            missing.append("GTIN or brand and MPN")
        if not self.identity_verified_at:
            missing.append("identity verification")
        if not self.condition_verified_at:
            missing.append("condition verification")
        if condition in {"used", "refurbished"} and not self.condition_notes.strip():
            missing.append("condition notes")
        if not self.actual_photos:
            missing.append("actual-photo confirmation")
        if not self.stock_confirmed_at:
            missing.append("stock verification date")
        if not self.price_verified_at:
            missing.append("price verification date")
        if not self.merchant_free_shipping and self.merchant_shipping_price is None:
            missing.append("shipping price or free-shipping confirmation")
        return missing

    @property
    def merchant_readiness_score(self) -> int:
        checks = 14
        missing = len(self.merchant_missing_fields())
        return max(0, round(((checks - min(checks, missing)) / checks) * 100))

    @property
    def is_merchant_ready(self) -> bool:
        return not self.merchant_missing_fields()

    def mark_verified_now(self) -> None:
        now = timezone.now()
        self.identity_verified_at = now
        self.condition_verified_at = now
        self.stock_confirmed_at = now
        self.price_verified_at = now



class HomepagePromotion(models.Model):
    """Staff-owned, scheduled storefront creative; never fabricates price or stock."""

    HERO = "hero"
    SIDE_TOP = "side_top"
    SIDE_BOTTOM = "side_bottom"
    SLOT_CHOICES = (
        (HERO, "Main hero"),
        (SIDE_TOP, "Upper promotion"),
        (SIDE_BOTTOM, "Lower promotion"),
    )
    slot = models.CharField(max_length=16, choices=SLOT_CHOICES, db_index=True)
    headline = models.CharField(max_length=90)
    eyebrow = models.CharField(max_length=48, blank=True)
    supporting_text = models.CharField(max_length=135, blank=True)
    button_label = models.CharField(max_length=32, default="Explore products")
    link_path = models.CharField(
        max_length=250, default="/catalog/",
        help_text="Internal path only (for example /catalog/ or /catalog/services/).",
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="homepage_promotions",
        help_text="Optional real product to illustrate the campaign.",
    )
    creative_image = models.ImageField(
        upload_to="homepage_campaigns/%Y/%m/", blank=True,
        help_text="Optional brand-approved creative. If empty, show the selected product's real photo.",
    )
    image_alt = models.CharField(max_length=140, blank=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slot", "-priority", "-updated_at", "-pk"]

    def __str__(self):
        return f"{self.get_slot_display()}: {self.headline}"

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        path = self.link_path.strip()
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or any(ord(char) < 32 for char in path)
        ):
            raise ValidationError({"link_path": "Use a local site path beginning with one slash."})
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError({"end_at": "End time must be after start time."})
        if self.is_active and self.product_id and not self.product.is_published:
            raise ValidationError({"product": "An active promotion needs a published product."})
        if self.creative_image and not self.image_alt.strip():
            raise ValidationError({"image_alt": "Describe the campaign image for screen readers."})

    @property
    def is_live(self):
        now = timezone.now()
        return (
            self.is_active
            and (not self.start_at or self.start_at <= now)
            and (not self.end_at or self.end_at > now)
            and (not self.product_id or self.product.is_published)
        )

    @property
    def destination(self):
        if self.product_id and self.product.is_published:
            return self.product.get_absolute_url()
        return self.link_path



class CommercialLandingPage(models.Model):
    slug = models.SlugField(unique=True, max_length=180)
    title = models.CharField(max_length=220)
    eyebrow = models.CharField(max_length=120, blank=True)
    meta_description = models.CharField(max_length=320)
    intro = models.TextField()
    buying_guidance = models.TextField(blank=True)
    category_keywords = models.CharField(
        max_length=300,
        blank=True,
        help_text="Comma-separated category words such as laptop, notebook.",
    )
    brand = models.CharField(max_length=120, blank=True)
    condition = models.CharField(max_length=20, blank=True)
    search_terms = models.CharField(
        max_length=400,
        blank=True,
        help_text="Comma-separated product-name and description terms.",
    )
    hero_cta = models.CharField(max_length=100, default="Request a quotation")
    hero_cta_url = models.CharField(max_length=240, default="/contact/?type=quote")
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:180]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return commercial_page_path(self.slug)

    @property
    def keyword_list(self) -> list[str]:
        combined = f"{self.category_keywords},{self.search_terms}"
        return [item.strip() for item in combined.split(",") if item.strip()]


class CommercialLandingFAQ(models.Model):
    page = models.ForeignKey(
        CommercialLandingPage,
        on_delete=models.CASCADE,
        related_name="faqs",
    )
    question = models.CharField(max_length=240)
    answer = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.question


class BuyingGuide(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(unique=True, max_length=220)
    excerpt = models.CharField(max_length=360)
    body = models.TextField()
    author_name = models.CharField(max_length=160, default="LEOSOFT Technical Team")
    reviewer_name = models.CharField(max_length=160, blank=True)
    keywords = models.CharField(max_length=320, blank=True)
    related_category_keywords = models.CharField(max_length=320, blank=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("buying_guide_detail", kwargs={"slug": self.slug})

    @property
    def keyword_list(self) -> list[str]:
        combined = f"{self.keywords},{self.related_category_keywords}"
        return [item.strip() for item in combined.split(",") if item.strip()]


class DeliveryZone(models.Model):
    name = models.CharField(max_length=140)
    areas = models.CharField(max_length=320)
    fee_from = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    lead_time = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class SearchQueryInsight(models.Model):
    query = models.CharField(max_length=500, db_index=True)
    page = models.URLField(blank=True)
    clicks = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)
    ctr = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    position = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-impressions", "position", "query"]
        indexes = [
            models.Index(
                fields=["query", "date_end"],
                name="merch_query_date_idx",
            )
        ]

    def __str__(self) -> str:
        return self.query
