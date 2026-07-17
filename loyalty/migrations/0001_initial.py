# Generated manually for Phase 7 consent and loyalty operations.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("crm", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerMarketingPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email_marketing", models.BooleanField(default=False)),
                ("whatsapp_marketing", models.BooleanField(default=False)),
                ("product_updates", models.BooleanField(default=False)),
                ("special_offers", models.BooleanField(default=False)),
                ("consent_source", models.CharField(choices=[("checkout", "Checkout"), ("portal", "Customer portal"), ("staff", "Staff recorded"), ("import", "Verified import")], default="portal", max_length=16)),
                ("consent_text_version", models.CharField(default="2026-07", max_length=32)),
                ("consented_at", models.DateTimeField(blank=True, null=True)),
                ("withdrawn_at", models.DateTimeField(blank=True, null=True)),
                ("unsubscribe_token", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="marketing_preference", to="crm.customer")),
            ],
            options={"ordering": ["customer__name", "customer_id"]},
        ),
        migrations.CreateModel(
            name="LoyaltyAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("points_balance", models.PositiveIntegerField(default=0)),
                ("lifetime_points", models.PositiveIntegerField(default=0)),
                ("tier", models.CharField(choices=[("member", "Member"), ("silver", "Silver"), ("gold", "Gold"), ("platinum", "Platinum")], db_index=True, default="member", max_length=16)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_account", to="crm.customer")),
            ],
            options={"ordering": ["-lifetime_points", "customer__name"]},
        ),
        migrations.CreateModel(
            name="LoyaltyTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("earn", "Points earned"), ("adjust", "Staff adjustment"), ("reverse", "Points reversed")], max_length=16)),
                ("points_delta", models.IntegerField()),
                ("idempotency_key", models.CharField(db_index=True, max_length=180, unique=True)),
                ("order_reference", models.CharField(blank=True, db_index=True, max_length=32)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="loyalty.loyaltyaccount")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=~models.Q(points_delta=0),
                        name="loyalty_points_delta_nonzero",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="MarketingConsentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("granted", "Consent granted"), ("updated", "Preferences updated"), ("withdrawn", "Consent withdrawn")], db_index=True, max_length=16)),
                ("source", models.CharField(choices=[("checkout", "Checkout"), ("portal", "Customer portal"), ("staff", "Staff recorded"), ("import", "Verified import")], max_length=16)),
                ("email_marketing", models.BooleanField(default=False)),
                ("whatsapp_marketing", models.BooleanField(default=False)),
                ("product_updates", models.BooleanField(default=False)),
                ("special_offers", models.BooleanField(default=False)),
                ("consent_text_version", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="marketing_consent_events", to="crm.customer")),
                ("preference", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="loyalty.customermarketingpreference")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
