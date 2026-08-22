from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class CustomerCampaign(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_WHATSAPP, "WhatsApp (manual click-to-chat)"),
    ]

    TOPIC_PRODUCT_UPDATES = "product_updates"
    TOPIC_SPECIAL_OFFERS = "special_offers"
    TOPIC_CHOICES = [
        (TOPIC_PRODUCT_UPDATES, "Product updates"),
        (TOPIC_SPECIAL_OFFERS, "Special offers"),
    ]

    SEGMENT_ALL = "all"
    SEGMENT_REPEAT = "repeat"
    SEGMENT_RECENT = "recent"
    SEGMENT_DORMANT = "dormant"
    SEGMENT_CHOICES = [
        (SEGMENT_ALL, "All eligible customers"),
        (SEGMENT_REPEAT, "Repeat customers"),
        (SEGMENT_RECENT, "Ordered in the last 90 days"),
        (SEGMENT_DORMANT, "No order for at least 90 days"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PREPARED = "prepared"
    STATUS_APPROVED = "approved"
    STATUS_SCHEDULED = "scheduled"
    STATUS_SENDING = "sending"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PREPARED, "Prepared"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_SENDING, "Sending"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Approval expired"),
        (STATUS_FAILED, "Failed"),
    ]

    name = models.CharField(max_length=180)
    marketing_campaign = models.ForeignKey(
        "marketing.MarketingCampaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaign_runs",
    )
    channel = models.CharField(
        max_length=16,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_EMAIL,
    )
    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES)
    segment = models.CharField(
        max_length=16,
        choices=SEGMENT_CHOICES,
        default=SEGMENT_ALL,
    )
    subject = models.CharField(max_length=200)
    body = models.TextField(
        help_text=(
            "Supported placeholders: {customer_name}, {first_name}, {company}, "
            "and {unsubscribe_url}."
        )
    )
    max_recipients = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    prepared_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    suppressed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    approval_note = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)

    automated_delivery = models.BooleanField(default=False, db_index=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    automation_batch_size = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    approval_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    pause_reason = models.CharField(max_length=240, blank=True)
    last_automation_at = models.DateTimeField(null=True, blank=True)
    automation_run_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_created",
    )
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_prepared",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_approved",
    )
    scheduled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_scheduled",
    )
    paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_paused",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaigns_sent",
    )
    prepared_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.name


class CustomerCampaignRecipient(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SENT = "sent"
    STATUS_SUPPRESSED = "suppressed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SENT, "Sent"),
        (STATUS_SUPPRESSED, "Suppressed"),
        (STATUS_FAILED, "Failed"),
    ]

    campaign = models.ForeignKey(
        CustomerCampaign,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    customer = models.ForeignKey(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name="customer_campaign_recipients",
    )
    email_address = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    suppression_reason = models.CharField(max_length=160, blank=True)
    consent_event = models.ForeignKey(
        "loyalty.MarketingConsentEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_recipients",
    )
    outbound_email = models.ForeignKey(
        "messaging.OutboundEmail",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaign_recipients",
    )
    prepared_at = models.DateTimeField(auto_now_add=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "customer__name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "customer"],
                name="unique_customer_per_campaign",
            )
        ]

    def __str__(self) -> str:
        return f"{self.campaign} — {self.email_address}"


class CampaignAutomationEvent(models.Model):
    ACTION_SCHEDULED = "scheduled"
    ACTION_BATCH_STARTED = "batch_started"
    ACTION_BATCH_FINISHED = "batch_finished"
    ACTION_PAUSED = "paused"
    ACTION_RESUMED = "resumed"
    ACTION_EXPIRED = "expired"
    ACTION_COMPLETED = "completed"
    ACTION_FAILED = "failed"
    ACTION_CANCELLED = "cancelled"
    ACTION_CHOICES = [
        (ACTION_SCHEDULED, "Scheduled"),
        (ACTION_BATCH_STARTED, "Automated batch started"),
        (ACTION_BATCH_FINISHED, "Automated batch finished"),
        (ACTION_PAUSED, "Paused"),
        (ACTION_RESUMED, "Resumed"),
        (ACTION_EXPIRED, "Approval expired"),
        (ACTION_COMPLETED, "Completed"),
        (ACTION_FAILED, "Failed"),
        (ACTION_CANCELLED, "Cancelled"),
    ]

    campaign = models.ForeignKey(
        CustomerCampaign,
        on_delete=models.CASCADE,
        related_name="automation_events",
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_campaign_automation_events",
    )
    message = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return f"{self.campaign} — {self.get_action_display()}"
