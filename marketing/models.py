import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def generate_link_code() -> str:
    """Generate a short, URL-safe campaign link code."""
    return secrets.token_urlsafe(7).replace("-", "").replace("_", "")[:10]


class SocialProfileSettings(models.Model):
    """Singleton social-profile links used across the public website."""

    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True, verbose_name="X / Twitter URL")
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Include the country code and digits only, for example 256700000000.",
    )
    default_share_message = models.CharField(
        max_length=240,
        blank=True,
        help_text="Optional short message added to product and service sharing text.",
    )

    class Meta:
        verbose_name = "Social media settings"
        verbose_name_plural = "Social media settings"

    def __str__(self) -> str:
        return "Social media settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SocialProfileSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def whatsapp_url(self) -> str:
        digits = "".join(ch for ch in self.whatsapp_number if ch.isdigit())
        return f"https://wa.me/{digits}" if digits else ""


class MarketingCampaign(models.Model):
    OBJECTIVE_AWARENESS = "awareness"
    OBJECTIVE_TRAFFIC = "traffic"
    OBJECTIVE_LEADS = "leads"
    OBJECTIVE_SALES = "sales"
    OBJECTIVE_ENGAGEMENT = "engagement"
    OBJECTIVE_CHOICES = [
        (OBJECTIVE_AWARENESS, "Brand awareness"),
        (OBJECTIVE_TRAFFIC, "Website traffic"),
        (OBJECTIVE_LEADS, "Lead generation"),
        (OBJECTIVE_SALES, "Sales"),
        (OBJECTIVE_ENGAGEMENT, "Engagement"),
    ]

    STATUS_PLANNED = "planned"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planned"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_COMPLETED, "Completed"),
    ]

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    objective = models.CharField(
        max_length=24, choices=OBJECTIVE_CHOICES, default=OBJECTIVE_TRAFFIC
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNED
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    target_audience = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_campaigns_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:180] or "campaign"
            candidate = base
            suffix = 2
            while MarketingCampaign.objects.exclude(pk=self.pk).filter(
                slug=candidate
            ).exists():
                candidate = f"{base[:190]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class CaptionTemplate(models.Model):
    CHANNEL_GENERAL = "general"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_FACEBOOK = "facebook"
    CHANNEL_INSTAGRAM = "instagram"
    CHANNEL_TIKTOK = "tiktok"
    CHANNEL_X = "x"
    CHANNEL_LINKEDIN = "linkedin"
    CHANNEL_YOUTUBE = "youtube"
    CHANNEL_CHOICES = [
        (CHANNEL_GENERAL, "General / multi-platform"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_FACEBOOK, "Facebook"),
        (CHANNEL_INSTAGRAM, "Instagram"),
        (CHANNEL_TIKTOK, "TikTok"),
        (CHANNEL_X, "X"),
        (CHANNEL_LINKEDIN, "LinkedIn"),
        (CHANNEL_YOUTUBE, "YouTube"),
    ]

    name = models.CharField(max_length=160)
    channel = models.CharField(
        max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_GENERAL
    )
    body = models.TextField(
        help_text=(
            "Available placeholders: {product_name}, {price}, {currency}, "
            "{category}, {url}, {company}, {hashtags}."
        )
    )
    hashtags = models.CharField(max_length=400, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_caption_templates_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["channel", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_channel_display()})"


class CampaignLink(models.Model):
    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="links",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_links",
    )
    name = models.CharField(max_length=180)
    code = models.CharField(
        max_length=16, unique=True, default=generate_link_code, editable=False
    )
    destination_url = models.URLField()
    source = models.CharField(max_length=60, default="direct")
    medium = models.CharField(max_length=60, default="social")
    content = models.CharField(max_length=120, blank=True)
    click_count = models.PositiveBigIntegerField(default=0)
    lead_count = models.PositiveBigIntegerField(default=0)
    last_clicked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_links_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "name"]

    def __str__(self) -> str:
        return self.name

    def get_tracking_path(self) -> str:
        return reverse("marketing_track", kwargs={"code": self.code})

    def destination_with_utm(self) -> str:
        parts = urlsplit(self.destination_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(
            {
                "utm_source": self.source,
                "utm_medium": self.medium,
                "utm_campaign": self.campaign.slug if self.campaign else "leosoft",
                "utm_content": self.content or self.code,
            }
        )
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )


class CampaignClick(models.Model):
    link = models.ForeignKey(
        CampaignLink, on_delete=models.CASCADE, related_name="click_events"
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    referrer = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return f"{self.link.code} at {self.occurred_at:%Y-%m-%d %H:%M}"


class ScheduledPost(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SCHEDULED = "scheduled"
    STATUS_READY = "ready"
    STATUS_PUBLISHED = "published"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_READY, "Ready to publish"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_marketing_posts",
    )
    title = models.CharField(max_length=200)
    caption = models.TextField()
    channels = models.JSONField(default=list)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    external_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_posts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_due(self) -> bool:
        return bool(
            self.status == self.STATUS_SCHEDULED
            and self.scheduled_for
            and self.scheduled_for <= timezone.now()
        )


class MarketingLead(models.Model):
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_QUALIFIED = "qualified"
    STATUS_WON = "won"
    STATUS_LOST = "lost"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_QUALIFIED, "Qualified"),
        (STATUS_WON, "Won"),
        (STATUS_LOST, "Lost"),
    ]

    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    link = models.ForeignKey(
        CampaignLink,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_records",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketing_leads",
    )
    contact_message_id = models.PositiveBigIntegerField(
        null=True, blank=True, unique=True
    )
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=60, default="direct")
    medium = models.CharField(max_length=60, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW
    )
    estimated_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_marketing_leads",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name} — {self.source}"
