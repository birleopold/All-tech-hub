from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class OutboundEmail(models.Model):
    CATEGORY_TRANSACTIONAL = "transactional"
    CATEGORY_MARKETING = "marketing"
    CATEGORY_SYSTEM = "system"
    CATEGORY_CHOICES = [
        (CATEGORY_TRANSACTIONAL, "Transactional"),
        (CATEGORY_MARKETING, "Marketing"),
        (CATEGORY_SYSTEM, "System"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_SUPPRESSED = "suppressed"
    STATUS_SENT = "sent"
    STATUS_DELIVERED = "delivered"
    STATUS_SOFT_BOUNCED = "soft_bounced"
    STATUS_BOUNCED = "bounced"
    STATUS_COMPLAINED = "complained"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SUPPRESSED, "Suppressed"),
        (STATUS_SENT, "Accepted by SMTP"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_SOFT_BOUNCED, "Soft bounced"),
        (STATUS_BOUNCED, "Hard bounced"),
        (STATUS_COMPLAINED, "Complaint received"),
        (STATUS_FAILED, "Failed"),
    ]

    to_email = models.EmailField()
    normalized_to_email = models.EmailField(blank=True, db_index=True)
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_TRANSACTIONAL,
        db_index=True,
    )
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    error = models.TextField(blank=True)
    suppression_reason = models.CharField(max_length=200, blank=True)
    tracking_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    idempotency_key = models.CharField(
        max_length=180,
        blank=True,
        null=True,
        unique=True,
    )
    provider = models.CharField(max_length=60, blank=True)
    provider_message_id = models.CharField(max_length=240, blank=True, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="outbound_emails_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    complained_at = models.DateTimeField(null=True, blank=True)
    suppressed_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True, db_index=True)

    commercial_document = models.ForeignKey(
        "billing.CommercialDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )
    job_card = models.ForeignKey(
        "operations.JobCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="outbound_status_created_idx",
            ),
            models.Index(
                fields=["normalized_to_email", "category"],
                name="outbound_email_category_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.to_email} — {self.subject}"

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.STATUS_DELIVERED,
            self.STATUS_BOUNCED,
            self.STATUS_COMPLAINED,
            self.STATUS_SUPPRESSED,
        }

    @property
    def can_retry(self) -> bool:
        return self.status in {
            self.STATUS_FAILED,
            self.STATUS_SOFT_BOUNCED,
            self.STATUS_SUPPRESSED,
        }

    def mark_sent(self) -> None:
        now = timezone.now()
        self.status = self.STATUS_SENT
        self.sent_at = now
        self.accepted_at = now
        self.last_event_at = now
        self.error = ""
        self.suppression_reason = ""

    def mark_failed(self, error: str) -> None:
        self.status = self.STATUS_FAILED
        self.error = (error or "Email delivery failed.")[:4000]
        self.last_event_at = timezone.now()

    def mark_suppressed(self, reason: str) -> None:
        now = timezone.now()
        self.status = self.STATUS_SUPPRESSED
        self.suppression_reason = (reason or "active_suppression")[:200]
        self.suppressed_at = now
        self.last_event_at = now


class EmailSuppression(models.Model):
    SCOPE_ALL = "all"
    SCOPE_MARKETING = "marketing"
    SCOPE_CHOICES = [
        (SCOPE_ALL, "All email"),
        (SCOPE_MARKETING, "Marketing only"),
    ]

    REASON_HARD_BOUNCE = "hard_bounce"
    REASON_COMPLAINT = "complaint"
    REASON_INVALID = "invalid_address"
    REASON_REPEATED_SOFT_BOUNCE = "repeated_soft_bounce"
    REASON_MANUAL = "manual"
    REASON_CHOICES = [
        (REASON_HARD_BOUNCE, "Hard bounce"),
        (REASON_COMPLAINT, "Spam complaint"),
        (REASON_INVALID, "Invalid address"),
        (REASON_REPEATED_SOFT_BOUNCE, "Repeated soft bounce"),
        (REASON_MANUAL, "Manual block"),
    ]

    SOURCE_PROVIDER = "provider"
    SOURCE_SYSTEM = "system"
    SOURCE_STAFF = "staff"
    SOURCE_CHOICES = [
        (SOURCE_PROVIDER, "Delivery provider"),
        (SOURCE_SYSTEM, "LEOSOFT system"),
        (SOURCE_STAFF, "Staff review"),
    ]

    email_address = models.EmailField(unique=True)
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default=SCOPE_ALL)
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_SYSTEM)
    is_active = models.BooleanField(default=True, db_index=True)
    event_count = models.PositiveIntegerField(default=1)
    details = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_suppressions_created",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_suppressions_released",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "-last_seen_at", "email_address"]

    def __str__(self) -> str:
        return f"{self.email_address} — {self.get_reason_display()}"


class EmailDeliveryEvent(models.Model):
    TYPE_ACCEPTED = "accepted"
    TYPE_DELIVERED = "delivered"
    TYPE_SOFT_BOUNCE = "soft_bounce"
    TYPE_HARD_BOUNCE = "hard_bounce"
    TYPE_COMPLAINT = "complaint"
    TYPE_SUPPRESSED = "suppressed"
    TYPE_FAILED = "failed"
    TYPE_CHOICES = [
        (TYPE_ACCEPTED, "Accepted"),
        (TYPE_DELIVERED, "Delivered"),
        (TYPE_SOFT_BOUNCE, "Soft bounce"),
        (TYPE_HARD_BOUNCE, "Hard bounce"),
        (TYPE_COMPLAINT, "Complaint"),
        (TYPE_SUPPRESSED, "Suppressed"),
        (TYPE_FAILED, "Failed"),
    ]

    event_key = models.CharField(max_length=240, unique=True)
    outbound_email = models.ForeignKey(
        OutboundEmail,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_events",
    )
    email_address = models.EmailField(db_index=True)
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    provider = models.CharField(max_length=60, blank=True)
    provider_message_id = models.CharField(max_length=240, blank=True, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["email_address", "event_type", "occurred_at"],
                name="email_event_address_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.email_address} — {self.get_event_type_display()}"
