# Generated manually for Phase 9 scheduled campaign operations.

from datetime import timedelta

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_active_approval_expiry(apps, schema_editor):
    CustomerCampaign = apps.get_model("customer_campaigns", "CustomerCampaign")
    for campaign in CustomerCampaign.objects.filter(
        status__in=["approved", "sending"],
        approved_at__isnull=False,
        approval_expires_at__isnull=True,
    ).iterator():
        campaign.approval_expires_at = campaign.approved_at + timedelta(hours=48)
        campaign.save(update_fields=["approval_expires_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("customer_campaigns", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="customercampaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("prepared", "Prepared"),
                    ("approved", "Approved"),
                    ("scheduled", "Scheduled"),
                    ("sending", "Sending"),
                    ("paused", "Paused"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Approval expired"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="automated_delivery",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="next_run_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="automation_batch_size",
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="approval_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="scheduled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="paused_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="pause_reason",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="last_automation_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="automation_run_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="scheduled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="customer_campaigns_scheduled",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="customercampaign",
            name="paused_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="customer_campaigns_paused",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="CampaignAutomationEvent",
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
                            ("scheduled", "Scheduled"),
                            ("batch_started", "Automated batch started"),
                            ("batch_finished", "Automated batch finished"),
                            ("paused", "Paused"),
                            ("resumed", "Resumed"),
                            ("expired", "Approval expired"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                ("message", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="customer_campaign_automation_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="automation_events",
                        to="customer_campaigns.customercampaign",
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.RunPython(populate_active_approval_expiry, migrations.RunPython.noop),
    ]
