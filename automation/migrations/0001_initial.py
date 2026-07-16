# Generated manually for Phase 3 durable automation.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("marketing", "0002_marketing_automation"),
    ]

    operations = [
        migrations.CreateModel(
            name="PostAutomationPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("manual", "Manual publishing"),
                            ("automatic", "Automatic where connected"),
                        ],
                        default="manual",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("queued", "Queued"),
                            ("running", "Publishing"),
                            ("manual", "Manual action required"),
                            ("partial", "Partially published"),
                            ("published", "Published"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="scheduled",
                        max_length=16,
                    ),
                ),
                (
                    "media_url",
                    models.URLField(
                        blank=True,
                        help_text="Optional public HTTPS image URL used for automatic social publishing.",
                    ),
                ),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "post",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="automation_plan",
                        to="marketing.scheduledpost",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.CreateModel(
            name="PostChannelDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("channel", models.CharField(max_length=32)),
                (
                    "method",
                    models.CharField(
                        choices=[
                            ("automatic", "Automatic"),
                            ("manual", "Manual"),
                        ],
                        default="manual",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("queued", "Queued"),
                            ("running", "Publishing"),
                            ("retrying", "Retrying"),
                            ("published", "Published"),
                            ("manual", "Manual action required"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("external_id", models.CharField(blank=True, max_length=200)),
                ("external_url", models.URLField(blank=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="automation.postautomationplan",
                    ),
                ),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channel_deliveries",
                        to="marketing.scheduledpost",
                    ),
                ),
            ],
            options={
                "ordering": ["post_id", "channel"],
                "indexes": [
                    models.Index(
                        fields=["status", "next_attempt_at"],
                        name="delivery_due_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("post", "channel"),
                        name="unique_post_channel_delivery",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="AutomationJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(db_index=True, max_length=180, unique=True),
                ),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("social_post", "Social post"),
                            ("saved_cart_email", "Saved-cart email"),
                            ("stock_alert_email", "Stock alert email"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("retry", "Retry scheduled"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("scheduled_for", models.DateTimeField(db_index=True)),
                ("next_attempt_at", models.DateTimeField(db_index=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=5)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("locked_by", models.CharField(blank=True, max_length=120)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "delivery",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="job",
                        to="automation.postchanneldelivery",
                    ),
                ),
            ],
            options={
                "ordering": ["next_attempt_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["status", "next_attempt_at"],
                        name="automation_job_due_idx",
                    )
                ],
            },
        ),
    ]
