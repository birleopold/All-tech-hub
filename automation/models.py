from __future__ import annotations

from django.db import models


class PostAutomationPlan(models.Model):
    MODE_MANUAL = "manual"
    MODE_AUTOMATIC = "automatic"
    MODE_CHOICES = [
        (MODE_MANUAL, "Manual publishing"),
        (MODE_AUTOMATIC, "Automatic where connected"),
    ]

    STATUS_SCHEDULED = "scheduled"
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_MANUAL = "manual"
    STATUS_PARTIAL = "partial"
    STATUS_PUBLISHED = "published"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Publishing"),
        (STATUS_MANUAL, "Manual action required"),
        (STATUS_PARTIAL, "Partially published"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    post = models.OneToOneField(
        "marketing.ScheduledPost",
        on_delete=models.CASCADE,
        related_name="automation_plan",
    )
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_MANUAL)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
        db_index=True,
    )
    media_url = models.URLField(
        blank=True,
        help_text="Optional public HTTPS image URL used for automatic social publishing.",
    )
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.post.title} — {self.get_status_display()}"


class PostChannelDelivery(models.Model):
    METHOD_AUTOMATIC = "automatic"
    METHOD_MANUAL = "manual"
    METHOD_CHOICES = [
        (METHOD_AUTOMATIC, "Automatic"),
        (METHOD_MANUAL, "Manual"),
    ]

    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_RETRYING = "retrying"
    STATUS_PUBLISHED = "published"
    STATUS_MANUAL = "manual"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Publishing"),
        (STATUS_RETRYING, "Retrying"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_MANUAL, "Manual action required"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    plan = models.ForeignKey(
        PostAutomationPlan,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    post = models.ForeignKey(
        "marketing.ScheduledPost",
        on_delete=models.CASCADE,
        related_name="channel_deliveries",
    )
    channel = models.CharField(max_length=32)
    method = models.CharField(
        max_length=16,
        choices=METHOD_CHOICES,
        default=METHOD_MANUAL,
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    external_id = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["post_id", "channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["post", "channel"],
                name="unique_post_channel_delivery",
            )
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="delivery_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.post.title} — {self.channel} — {self.get_status_display()}"


class AutomationJob(models.Model):
    TYPE_SOCIAL_POST = "social_post"
    TYPE_SAVED_CART_EMAIL = "saved_cart_email"
    TYPE_STOCK_ALERT_EMAIL = "stock_alert_email"
    TYPE_CHOICES = [
        (TYPE_SOCIAL_POST, "Social post"),
        (TYPE_SAVED_CART_EMAIL, "Saved-cart email"),
        (TYPE_STOCK_ALERT_EMAIL, "Stock alert email"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_RETRY = "retry"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_RETRY, "Retry scheduled"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    idempotency_key = models.CharField(max_length=180, unique=True, db_index=True)
    job_type = models.CharField(max_length=32, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    delivery = models.OneToOneField(
        PostChannelDelivery,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="job",
    )
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    scheduled_for = models.DateTimeField(db_index=True)
    next_attempt_at = models.DateTimeField(db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=120, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["next_attempt_at", "id"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="automation_job_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.job_type}:{self.idempotency_key}"

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.STATUS_SUCCEEDED,
            self.STATUS_FAILED,
            self.STATUS_CANCELLED,
        }
