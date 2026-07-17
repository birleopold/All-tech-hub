# Generated manually for Phase 11 email deliverability and suppression.

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_outbound_delivery_fields(apps, schema_editor):
    OutboundEmail = apps.get_model("messaging", "OutboundEmail")
    for row in OutboundEmail.objects.all().iterator():
        normalized = (row.to_email or "").strip().lower()
        updates = {
            "normalized_to_email": normalized,
            "tracking_token": uuid.uuid4(),
        }
        if row.status == "sent" and row.sent_at:
            updates["accepted_at"] = row.sent_at
            updates["last_event_at"] = row.sent_at
        elif row.status == "failed" and row.sent_at:
            updates["last_event_at"] = row.sent_at
        OutboundEmail.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("messaging", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboundemail",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="bounced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="category",
            field=models.CharField(
                choices=[
                    ("transactional", "Transactional"),
                    ("marketing", "Marketing"),
                    ("system", "System"),
                ],
                db_index=True,
                default="transactional",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="complained_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=180, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="last_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="last_event_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="normalized_to_email",
            field=models.EmailField(blank=True, db_index=True, max_length=254),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="provider",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="provider_message_id",
            field=models.CharField(blank=True, db_index=True, max_length=240),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="suppressed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="suppression_reason",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="tracking_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="outboundemail",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="outboundemail",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("suppressed", "Suppressed"),
                    ("sent", "Accepted by SMTP"),
                    ("delivered", "Delivered"),
                    ("soft_bounced", "Soft bounced"),
                    ("bounced", "Hard bounced"),
                    ("complained", "Complaint received"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="queued",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="EmailSuppression",
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
                ("email_address", models.EmailField(max_length=254, unique=True)),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("all", "All email"),
                            ("marketing", "Marketing only"),
                        ],
                        default="all",
                        max_length=16,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("hard_bounce", "Hard bounce"),
                            ("complaint", "Spam complaint"),
                            ("invalid_address", "Invalid address"),
                            ("repeated_soft_bounce", "Repeated soft bounce"),
                            ("manual", "Manual block"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("provider", "Delivery provider"),
                            ("system", "LEOSOFT system"),
                            ("staff", "Staff review"),
                        ],
                        default="system",
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("event_count", models.PositiveIntegerField(default=1)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "last_seen_at",
                    models.DateTimeField(db_index=True, default=django.utils.timezone.now),
                ),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("release_reason", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="email_suppressions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="email_suppressions_released",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-is_active", "-last_seen_at", "email_address"],
            },
        ),
        migrations.CreateModel(
            name="EmailDeliveryEvent",
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
                ("event_key", models.CharField(max_length=240, unique=True)),
                ("email_address", models.EmailField(db_index=True, max_length=254)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("delivered", "Delivered"),
                            ("soft_bounce", "Soft bounce"),
                            ("hard_bounce", "Hard bounce"),
                            ("complaint", "Complaint"),
                            ("suppressed", "Suppressed"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("provider", models.CharField(blank=True, max_length=60)),
                (
                    "provider_message_id",
                    models.CharField(blank=True, db_index=True, max_length=240),
                ),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "outbound_email",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="delivery_events",
                        to="messaging.outboundemail",
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="outboundemail",
            index=models.Index(
                fields=["status", "created_at"],
                name="outbound_status_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="outboundemail",
            index=models.Index(
                fields=["normalized_to_email", "category"],
                name="outbound_email_category_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="emaildeliveryevent",
            index=models.Index(
                fields=["email_address", "event_type", "occurred_at"],
                name="email_event_address_idx",
            ),
        ),
        migrations.RunPython(
            backfill_outbound_delivery_fields,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="outboundemail",
            name="tracking_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
