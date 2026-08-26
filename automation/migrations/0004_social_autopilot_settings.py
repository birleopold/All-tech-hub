from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("automation", "0003_register_order_notification_job_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialAutopilotSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("singleton_key", models.CharField(default="primary", editable=False, max_length=32, unique=True)),
                ("enabled", models.BooleanField(db_index=True, default=False)),
                ("mode", models.CharField(choices=[("controlled", "Controlled — create drafts for review"), ("full", "Full autopilot — schedule and publish")], default="controlled", max_length=16)),
                ("channels", models.JSONField(blank=True, default=list, help_text="Enabled zero-cost publishing channels.")),
                ("posts_per_day", models.PositiveSmallIntegerField(default=1)),
                ("posting_hours", models.JSONField(blank=True, default=list, help_text="Kampala-local hours, for example [9, 18].")),
                ("queue_days", models.PositiveSmallIntegerField(default=3)),
                ("product_cooldown_days", models.PositiveSmallIntegerField(default=7)),
                ("include_prices", models.BooleanField(default=True)),
                ("require_in_stock", models.BooleanField(default=True)),
                ("default_hashtags", models.CharField(blank=True, default="#LEOSOFT #TechnologyUganda #Kampala", max_length=300)),
                ("last_generated_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("preferred_product", models.ForeignKey(blank=True, help_text="Optional one-time priority product; cleared after calendar generation.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="autopilot_preferences", to="catalog.product")),
            ],
            options={
                "verbose_name": "Social autopilot settings",
                "verbose_name_plural": "Social autopilot settings",
            },
        ),
    ]
