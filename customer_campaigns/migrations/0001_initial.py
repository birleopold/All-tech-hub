# Generated manually for Phase 8 controlled customer campaigns.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("loyalty", "0001_initial"),
        ("marketing", "__latest__"),
        ("messaging", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("channel", models.CharField(choices=[("email", "Email")], default="email", max_length=16)),
                ("topic", models.CharField(choices=[("product_updates", "Product updates"), ("special_offers", "Special offers")], max_length=32)),
                ("segment", models.CharField(choices=[("all", "All eligible customers"), ("repeat", "Repeat customers"), ("recent", "Ordered in the last 90 days"), ("dormant", "No order for at least 90 days")], default="all", max_length=16)),
                ("subject", models.CharField(max_length=200)),
                ("body", models.TextField(help_text="Supported placeholders: {customer_name}, {first_name}, {company}, and {unsubscribe_url}.")),
                ("max_recipients", models.PositiveSmallIntegerField(default=20, validators=[django.core.validators.MinValueValidator(1)])),
                ("status", models.CharField(choices=[("draft", "Draft"), ("prepared", "Prepared"), ("approved", "Approved"), ("sending", "Sending"), ("completed", "Completed"), ("cancelled", "Cancelled"), ("failed", "Failed")], db_index=True, default="draft", max_length=16)),
                ("prepared_count", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("suppressed_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("approval_note", models.TextField(blank=True)),
                ("failure_reason", models.TextField(blank=True)),
                ("prepared_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaigns_approved", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaigns_created", to=settings.AUTH_USER_MODEL)),
                ("marketing_campaign", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaign_runs", to="marketing.marketingcampaign")),
                ("prepared_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaigns_prepared", to=settings.AUTH_USER_MODEL)),
                ("sent_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaigns_sent", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CustomerCampaignRecipient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email_address", models.EmailField(max_length=254)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("sent", "Sent"), ("suppressed", "Suppressed"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)),
                ("suppression_reason", models.CharField(blank=True, max_length=160)),
                ("prepared_at", models.DateTimeField(auto_now_add=True)),
                ("attempted_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipients", to="customer_campaigns.customercampaign")),
                ("consent_event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="campaign_recipients", to="loyalty.marketingconsentevent")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customer_campaign_recipients", to="crm.customer")),
                ("outbound_email", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_campaign_recipients", to="messaging.outboundemail")),
            ],
            options={
                "ordering": ["status", "customer__name", "id"],
                "constraints": [models.UniqueConstraint(fields=("campaign", "customer"), name="unique_customer_per_campaign")],
            },
        ),
    ]
