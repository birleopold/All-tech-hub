# Generated manually for Phase 10 automation control and recovery.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_primary_control(apps, schema_editor):
    AutomationControl = apps.get_model("automation", "AutomationControl")
    AutomationControl.objects.get_or_create(singleton_key="primary")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("automation", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AutomationControl",
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
                    "singleton_key",
                    models.CharField(
                        default="primary",
                        editable=False,
                        max_length=32,
                        unique=True,
                    ),
                ),
                ("is_paused", models.BooleanField(db_index=True, default=False)),
                (
                    "paused_job_types",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Automation job type values that workers must not claim.",
                    ),
                ),
                ("pause_reason", models.CharField(blank=True, max_length=300)),
                ("paused_at", models.DateTimeField(blank=True, null=True)),
                ("resumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_heartbeat_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("last_run_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_run_status",
                    models.CharField(
                        choices=[
                            ("never", "Never run"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("partial", "Completed with failures"),
                            ("failed", "Failed"),
                            ("paused", "Paused"),
                            ("dry_run", "Dry run"),
                        ],
                        default="never",
                        max_length=16,
                    ),
                ),
                ("last_worker_id", models.CharField(blank=True, max_length=160)),
                ("last_summary", models.JSONField(blank=True, default=dict)),
                ("consecutive_failures", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "paused_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="automation_pauses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resumed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="automation_resumes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Automation control",
                "verbose_name_plural": "Automation control",
            },
        ),
        migrations.CreateModel(
            name="AutomationRun",
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
                    "source",
                    models.CharField(
                        choices=[
                            ("timer", "Timer"),
                            ("manual", "Manual command"),
                            ("health", "Health check"),
                        ],
                        default="timer",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("partial", "Completed with failures"),
                            ("failed", "Failed"),
                            ("paused", "Paused"),
                            ("dry_run", "Dry run"),
                        ],
                        db_index=True,
                        default="running",
                        max_length=16,
                    ),
                ),
                ("worker_id", models.CharField(blank=True, max_length=160)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-started_at", "-id"]},
        ),
        migrations.CreateModel(
            name="AutomationJobEvent",
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
                    "action",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("claimed", "Claimed"),
                            ("succeeded", "Succeeded"),
                            ("retry", "Retry scheduled"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("replayed", "Replayed"),
                            ("recovered", "Recovered stale lock"),
                            ("blocked", "Replay blocked"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("message", models.CharField(blank=True, max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="automation_job_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="automation.automationjob",
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.RunPython(
            create_primary_control,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
