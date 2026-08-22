import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class GrowthSettings(models.Model):
    """Singleton integration and automation settings for growth marketing."""

    ga4_measurement_id = models.CharField(
        max_length=32,
        blank=True,
        help_text="Google Analytics 4 measurement ID, for example G-XXXXXXXXXX.",
    )
    search_console_verification_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="Only the content value supplied by Google Search Console.",
    )
    clarity_project_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Microsoft Clarity project ID.",
    )
    require_analytics_consent = models.BooleanField(
        default=True,
        help_text="Show a consent choice before loading Analytics and Clarity.",
    )
    privacy_policy_url = models.URLField(blank=True)

    google_business_profile_url = models.URLField(blank=True)
    google_review_url = models.URLField(blank=True)
    google_place_id = models.CharField(max_length=255, blank=True)

    merchant_country = models.CharField(max_length=2, default="UG")
    merchant_language = models.CharField(max_length=8, default="en")
    merchant_default_brand = models.CharField(
        max_length=120,
        blank=True,
        help_text="Use only when LEOSOFT is genuinely the product brand.",
    )
    merchant_shipping_service = models.CharField(
        max_length=120, default="Standard delivery"
    )
    merchant_shipping_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    merchant_return_policy_url = models.URLField(blank=True)

    abandoned_cart_enabled = models.BooleanField(default=True)
    abandoned_cart_first_delay_hours = models.PositiveIntegerField(default=1)
    abandoned_cart_second_delay_hours = models.PositiveIntegerField(default=24)
    back_in_stock_enabled = models.BooleanField(default=True)
    default_content_hashtags = models.CharField(
        max_length=400,
        blank=True,
        default="#LEOSOFT #TechnologyUganda #ComputersUganda",
    )

    class Meta:
        verbose_name = "Growth integration settings"
        verbose_name_plural = "Growth integration settings"

    def __str__(self) -> str:
        return "Growth integration settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.ga4_measurement_id = self.ga4_measurement_id.strip().upper()
        self.merchant_country = self.merchant_country.strip().upper() or "UG"
        self.merchant_language = self.merchant_language.strip().lower() or "en"
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "GrowthSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ProductGrowthData(models.Model):
    CONDITION_NEW = "new"
    CONDITION_REFURBISHED = "refurbished"
    CONDITION_USED = "used"
    CONDITION_CHOICES = [
        (CONDITION_NEW, "New"),
        (CONDITION_REFURBISHED, "Refurbished"),
        (CONDITION_USED, "Used"),
    ]

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="growth_data",
    )
    brand = models.CharField(max_length=120, blank=True)
    gtin = models.CharField(
        max_length=32,
        blank=True,
        help_text="UPC, EAN, JAN or ISBN digits when the manufacturer assigned one.",
    )
    mpn = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Manufacturer part number",
    )
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default=CONDITION_NEW,
    )
    google_product_category = models.CharField(max_length=255, blank=True)
    custom_label_0 = models.CharField(max_length=100, blank=True)
    shipping_label = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name"]
        verbose_name = "Product feed metadata"
        verbose_name_plural = "Product feed metadata"

    def __str__(self) -> str:
        return f"Feed data — {self.product.name}"


class StockAlertSubscription(models.Model):
    ALERT_BACK_IN_STOCK = "back_in_stock"
    ALERT_PRICE_DROP = "price_drop"
    ALERT_CHOICES = [
        (ALERT_BACK_IN_STOCK, "Back in stock"),
        (ALERT_PRICE_DROP, "Price drop"),
    ]

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="growth_stock_alerts",
    )
    email = models.EmailField()
    phone = models.CharField(max_length=64, blank=True)
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_CHOICES,
        default=ALERT_BACK_IN_STOCK,
    )
    target_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "email", "alert_type"],
                name="unique_growth_product_email_alert",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} — {self.product.name}"


class SavedCart(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_RECOVERED = "recovered"
    STATUS_UNSUBSCRIBED = "unsubscribed"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RECOVERED, "Recovered"),
        (STATUS_UNSUBSCRIBED, "Unsubscribed"),
        (STATUS_EXPIRED, "Expired"),
    ]

    session_key = models.CharField(max_length=64, db_index=True)
    customer_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=64, blank=True)
    cart_data = models.JSONField(default=dict)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    recovery_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )
    consent_at = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now, db_index=True)
    first_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    second_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    recovered_order = models.ForeignKey(
        "commerce.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recovered_saved_carts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity", "-id"]

    def __str__(self) -> str:
        return f"Saved cart — {self.email}"

    def get_recovery_path(self) -> str:
        return reverse(
            "growth_saved_cart_recover",
            kwargs={"token": self.recovery_token},
        )


class ContentAsset(models.Model):
    TYPE_WHATSAPP = "whatsapp"
    TYPE_SOCIAL_CAPTION = "social_caption"
    TYPE_TIKTOK_SCRIPT = "tiktok_script"
    TYPE_LINKEDIN = "linkedin"
    TYPE_EMAIL = "email"
    TYPE_POSTER = "poster"
    TYPE_CHOICES = [
        (TYPE_WHATSAPP, "WhatsApp / Status caption"),
        (TYPE_SOCIAL_CAPTION, "Facebook / Instagram caption"),
        (TYPE_TIKTOK_SCRIPT, "TikTok / Reels script"),
        (TYPE_LINKEDIN, "LinkedIn business post"),
        (TYPE_EMAIL, "Email promotion"),
        (TYPE_POSTER, "Poster copy"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_APPROVED = "approved"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="growth_content_assets",
    )
    campaign = models.ForeignKey(
        "marketing.MarketingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="growth_content_assets",
    )
    asset_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="growth_content_assets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class DistributionGroup(models.Model):
    PLATFORM_FACEBOOK = "facebook"
    PLATFORM_WHATSAPP = "whatsapp"
    PLATFORM_TELEGRAM = "telegram"
    PLATFORM_LINKEDIN = "linkedin"
    PLATFORM_OTHER = "other"
    PLATFORM_CHOICES = [
        (PLATFORM_FACEBOOK, "Facebook group"),
        (PLATFORM_WHATSAPP, "WhatsApp group / community"),
        (PLATFORM_TELEGRAM, "Telegram group / channel"),
        (PLATFORM_LINKEDIN, "LinkedIn group"),
        (PLATFORM_OTHER, "Other platform"),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    name = models.CharField(max_length=180)
    url = models.URLField()
    audience = models.CharField(max_length=240, blank=True)
    rules = models.TextField(blank=True)
    best_posting_times = models.CharField(max_length=240, blank=True)
    tracking_link = models.ForeignKey(
        "marketing.CampaignLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_groups",
    )
    last_posted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distribution_groups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["platform", "name"]

    def __str__(self) -> str:
        return self.name


class Ambassador(models.Model):
    COMMISSION_PERCENT = "percent"
    COMMISSION_FIXED = "fixed"
    COMMISSION_CHOICES = [
        (COMMISSION_PERCENT, "Percentage of order value"),
        (COMMISSION_FIXED, "Fixed amount per order"),
    ]

    name = models.CharField(max_length=180)
    code = models.SlugField(max_length=50, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    destination_url = models.URLField(blank=True)
    commission_type = models.CharField(
        max_length=12,
        choices=COMMISSION_CHOICES,
        default=COMMISSION_PERCENT,
    )
    commission_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    click_count = models.PositiveBigIntegerField(default=0)
    lead_count = models.PositiveBigIntegerField(default=0)
    order_count = models.PositiveBigIntegerField(default=0)
    revenue_total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ambassadors_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        base = slugify(self.code or self.name)[:40] or "ambassador"
        candidate = base
        suffix = 2
        while Ambassador.objects.exclude(pk=self.pk).filter(code=candidate).exists():
            candidate = f"{base[:44]}-{suffix}"
            suffix += 1
        self.code = candidate
        super().save(*args, **kwargs)

    def get_referral_path(self) -> str:
        return reverse("growth_ambassador_referral", kwargs={"code": self.code})

    def calculate_commission(self, revenue) -> Decimal:
        revenue = Decimal(revenue or 0)
        if self.commission_type == self.COMMISSION_FIXED:
            return max(Decimal("0"), self.commission_value)
        return max(
            Decimal("0"),
            (revenue * self.commission_value / Decimal("100")).quantize(
                Decimal("0.01")
            ),
        )


class AmbassadorClick(models.Model):
    ambassador = models.ForeignKey(
        Ambassador,
        on_delete=models.CASCADE,
        related_name="clicks",
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    referrer = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]


class AmbassadorLead(models.Model):
    ambassador = models.ForeignKey(
        Ambassador,
        on_delete=models.CASCADE,
        related_name="attributed_leads",
    )
    lead = models.OneToOneField(
        "marketing.MarketingLead",
        on_delete=models.CASCADE,
        related_name="ambassador_attribution",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AmbassadorConversion(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    ambassador = models.ForeignKey(
        Ambassador,
        on_delete=models.PROTECT,
        related_name="conversions",
    )
    order = models.OneToOneField(
        "commerce.Order",
        on_delete=models.PROTECT,
        related_name="ambassador_conversion",
    )
    revenue = models.DecimalField(max_digits=16, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ambassador_conversions_approved")
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ambassador_conversions_paid")
    payout_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.ambassador.code} — {self.order.reference}"
