from __future__ import annotations

from django.conf import settings
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
    TYPE_ORDER_CONFIRMATION_EMAIL = "order_confirmation_email"
    TYPE_ORDER_STATUS_EMAIL = "order_status_email"
    TYPE_CHOICES = [
        (TYPE_SOCIAL_POST, "Social post"),
        (TYPE_SAVED_CART_EMAIL, "Saved-cart email"),
        (TYPE_STOCK_ALERT_EMAIL, "Stock alert email"),
        (TYPE_ORDER_CONFIRMATION_EMAIL, "Order confirmation email"),
        (TYPE_ORDER_STATUS_EMAIL, "Order status email"),
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


class AutomationControl(models.Model):
    RUN_NEVER = "never"
    RUN_RUNNING = "running"
    RUN_SUCCEEDED = "succeeded"
    RUN_PARTIAL = "partial"
    RUN_FAILED = "failed"
    RUN_PAUSED = "paused"
    RUN_DRY = "dry_run"
    RUN_STATUS_CHOICES = [
        (RUN_NEVER, "Never run"),
        (RUN_RUNNING, "Running"),
        (RUN_SUCCEEDED, "Succeeded"),
        (RUN_PARTIAL, "Completed with failures"),
        (RUN_FAILED, "Failed"),
        (RUN_PAUSED, "Paused"),
        (RUN_DRY, "Dry run"),
    ]

    singleton_key = models.CharField(
        max_length=32,
        default="primary",
        unique=True,
        editable=False,
    )
    is_paused = models.BooleanField(default=False, db_index=True)
    paused_job_types = models.JSONField(
        default=list,
        blank=True,
        help_text="Automation job type values that workers must not claim.",
    )
    pause_reason = models.CharField(max_length=300, blank=True)
    paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_pauses",
    )
    paused_at = models.DateTimeField(null=True, blank=True)
    resumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_resumes",
    )
    resumed_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    last_run_finished_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        max_length=16,
        choices=RUN_STATUS_CHOICES,
        default=RUN_NEVER,
    )
    last_worker_id = models.CharField(max_length=160, blank=True)
    last_summary = models.JSONField(default=dict, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Automation control"
        verbose_name_plural = "Automation control"

    def __str__(self) -> str:
        return "Automation control"

    @classmethod
    def load(cls):
        row, _ = cls.objects.get_or_create(singleton_key="primary")
        return row


class AutomationRun(models.Model):
    SOURCE_TIMER = "timer"
    SOURCE_MANUAL = "manual"
    SOURCE_HEALTH = "health"
    SOURCE_CHOICES = [
        (SOURCE_TIMER, "Timer"),
        (SOURCE_MANUAL, "Manual command"),
        (SOURCE_HEALTH, "Health check"),
    ]

    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"
    STATUS_PAUSED = "paused"
    STATUS_DRY = "dry_run"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_PARTIAL, "Completed with failures"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_DRY, "Dry run"),
    ]

    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_TIMER)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
        db_index=True,
    )
    worker_id = models.CharField(max_length=160, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"Automation run {self.pk} — {self.get_status_display()}"


class AutomationJobEvent(models.Model):
    ACTION_QUEUED = "queued"
    ACTION_CLAIMED = "claimed"
    ACTION_SUCCEEDED = "succeeded"
    ACTION_RETRY = "retry"
    ACTION_FAILED = "failed"
    ACTION_CANCELLED = "cancelled"
    ACTION_REPLAYED = "replayed"
    ACTION_RECOVERED = "recovered"
    ACTION_BLOCKED = "blocked"
    ACTION_CHOICES = [
        (ACTION_QUEUED, "Queued"),
        (ACTION_CLAIMED, "Claimed"),
        (ACTION_SUCCEEDED, "Succeeded"),
        (ACTION_RETRY, "Retry scheduled"),
        (ACTION_FAILED, "Failed"),
        (ACTION_CANCELLED, "Cancelled"),
        (ACTION_REPLAYED, "Replayed"),
        (ACTION_RECOVERED, "Recovered stale lock"),
        (ACTION_BLOCKED, "Replay blocked"),
    ]

    job = models.ForeignKey(
        AutomationJob,
        on_delete=models.CASCADE,
        related_name="events",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_job_events",
    )
    message = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return f"{self.job} — {self.get_action_display()}"


class SocialAutopilotSettings(models.Model):
    MODE_CONTROLLED = "controlled"
    MODE_FULL = "full"
    MODE_CHOICES = [
        (MODE_CONTROLLED, "Controlled — create drafts for review"),
        (MODE_FULL, "Full autopilot — schedule and publish"),
    ]

    singleton_key = models.CharField(
        max_length=32, default="primary", unique=True, editable=False
    )
    enabled = models.BooleanField(default=False, db_index=True)
    mode = models.CharField(
        max_length=16, choices=MODE_CHOICES, default=MODE_CONTROLLED
    )
    channels = models.JSONField(
        default=list,
        blank=True,
        help_text="Enabled zero-cost publishing channels.",
    )
    posts_per_day = models.PositiveSmallIntegerField(default=1)
    posting_hours = models.JSONField(
        default=list,
        blank=True,
        help_text="Kampala-local hours, for example [9, 18].",
    )
    queue_days = models.PositiveSmallIntegerField(default=3)
    product_cooldown_days = models.PositiveSmallIntegerField(default=7)
    include_prices = models.BooleanField(default=True)
    require_in_stock = models.BooleanField(default=True)
    default_hashtags = models.CharField(
        max_length=300,
        default="#LEOSOFT #TechnologyUganda #Kampala",
        blank=True,
    )
    preferred_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="autopilot_preferences",
        help_text="Optional one-time priority product; cleared after calendar generation.",
    )
    last_generated_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Social autopilot settings"
        verbose_name_plural = "Social autopilot settings"

    def __str__(self) -> str:
        return "Social autopilot"

    @classmethod
    def load(cls):
        row, _ = cls.objects.get_or_create(
            singleton_key="primary",
            defaults={
                "channels": ["facebook", "instagram", "telegram"],
                "posting_hours": [9, 18],
            },
        )
        return row
