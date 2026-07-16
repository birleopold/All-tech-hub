# Generated manually for transaction reliability foundations.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("commerce", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderReservation",
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
                    models.CharField(db_index=True, max_length=128, unique=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("reserved", "Reserved"),
                            ("committed", "Committed"),
                            ("released", "Released"),
                            ("expired", "Expired"),
                        ],
                        db_index=True,
                        default="reserved",
                        max_length=16,
                    ),
                ),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("reserved_at", models.DateTimeField(auto_now_add=True)),
                ("committed_at", models.DateTimeField(blank=True, null=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("release_reason", models.CharField(blank=True, max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_reservations_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_reservation",
                        to="commerce.order",
                    ),
                ),
            ],
            options={"ordering": ["expires_at", "id"]},
        ),
        migrations.CreateModel(
            name="PaymentAttempt",
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
                    models.CharField(db_index=True, max_length=128, unique=True),
                ),
                ("provider", models.CharField(db_index=True, default="manual", max_length=64)),
                ("external_reference", models.CharField(blank=True, db_index=True, max_length=160)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("pending", "Pending"),
                            ("authorised", "Authorised"),
                            ("paid", "Paid"),
                            ("failed", "Failed"),
                            ("expired", "Expired"),
                            ("partial_refund", "Partially refunded"),
                            ("refunded", "Refunded"),
                            ("disputed", "Disputed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="created",
                        max_length=24,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="UGX", max_length=8)),
                (
                    "safe_metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Non-secret provider metadata only. Never store credentials or raw payment secrets.",
                    ),
                ),
                ("request_fingerprint", models.CharField(blank=True, max_length=64)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_attempts",
                        to="commerce.order",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="PaymentRefund",
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
                    models.CharField(db_index=True, max_length=128, unique=True),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.CharField(max_length=255)),
                ("external_reference", models.CharField(blank=True, max_length=160)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "payment_attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                        to="reliability.paymentattempt",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_attempt_refunds_processed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-processed_at", "-id"]},
        ),
        migrations.CreateModel(
            name="PaymentWebhookEvent",
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
                ("provider", models.CharField(max_length=64)),
                ("event_id", models.CharField(max_length=180)),
                ("payload_sha256", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("processed", "Processed"),
                            ("ignored", "Ignored"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="received",
                        max_length=16,
                    ),
                ),
                ("last_error", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "payment_attempt",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="webhook_events",
                        to="reliability.paymentattempt",
                    ),
                ),
            ],
            options={
                "ordering": ["-received_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "event_id"),
                        name="unique_provider_webhook_event",
                    )
                ],
            },
        ),
        migrations.AddIndex(
            model_name="orderreservation",
            index=models.Index(
                fields=["status", "expires_at"],
                name="reservation_due_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentattempt",
            index=models.Index(
                fields=["order", "status"],
                name="payment_order_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentattempt",
            index=models.Index(
                fields=["provider", "external_reference"],
                name="payment_provider_ref_idx",
            ),
        ),
    ]
