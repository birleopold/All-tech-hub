import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import marketing.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0009_category_parent"),
        ("marketing", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketingCampaign",
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
                ("name", models.CharField(max_length=180)),
                ("slug", models.SlugField(blank=True, max_length=200, unique=True)),
                (
                    "objective",
                    models.CharField(
                        choices=[
                            ("awareness", "Brand awareness"),
                            ("traffic", "Website traffic"),
                            ("leads", "Lead generation"),
                            ("sales", "Sales"),
                            ("engagement", "Engagement"),
                        ],
                        default="traffic",
                        max_length=24,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("active", "Active"),
                            ("paused", "Paused"),
                            ("completed", "Completed"),
                        ],
                        default="planned",
                        max_length=20,
                    ),
                ),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("budget", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("target_audience", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_campaigns_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "name"]},
        ),
        migrations.CreateModel(
            name="CaptionTemplate",
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
                ("name", models.CharField(max_length=160)),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("general", "General / multi-platform"),
                            ("whatsapp", "WhatsApp"),
                            ("facebook", "Facebook"),
                            ("instagram", "Instagram"),
                            ("tiktok", "TikTok"),
                            ("x", "X"),
                            ("linkedin", "LinkedIn"),
                            ("youtube", "YouTube"),
                        ],
                        default="general",
                        max_length=20,
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        help_text=(
                            "Available placeholders: {product_name}, {price}, {currency}, "
                            "{category}, {url}, {company}, {hashtags}."
                        )
                    ),
                ),
                ("hashtags", models.CharField(blank=True, max_length=400)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_caption_templates_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["channel", "name"]},
        ),
        migrations.CreateModel(
            name="CampaignLink",
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
                ("name", models.CharField(max_length=180)),
                (
                    "code",
                    models.CharField(
                        default=marketing.models.generate_link_code,
                        editable=False,
                        max_length=16,
                        unique=True,
                    ),
                ),
                ("destination_url", models.URLField()),
                ("source", models.CharField(default="direct", max_length=60)),
                ("medium", models.CharField(default="social", max_length=60)),
                ("content", models.CharField(blank=True, max_length=120)),
                ("click_count", models.PositiveBigIntegerField(default=0)),
                ("lead_count", models.PositiveBigIntegerField(default=0)),
                ("last_clicked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="links",
                        to="marketing.marketingcampaign",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_links_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_links",
                        to="catalog.product",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "name"]},
        ),
        migrations.CreateModel(
            name="CampaignClick",
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
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("session_key", models.CharField(blank=True, max_length=64)),
                ("ip_hash", models.CharField(blank=True, max_length=64)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("referrer", models.TextField(blank=True)),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="click_events",
                        to="marketing.campaignlink",
                    ),
                ),
            ],
            options={"ordering": ["-occurred_at", "-id"]},
        ),
        migrations.CreateModel(
            name="ScheduledPost",
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
                ("title", models.CharField(max_length=200)),
                ("caption", models.TextField()),
                ("channels", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("scheduled", "Scheduled"),
                            ("ready", "Ready to publish"),
                            ("published", "Published"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("scheduled_for", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("external_url", models.URLField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="posts",
                        to="marketing.marketingcampaign",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_posts_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_marketing_posts",
                        to="catalog.product",
                    ),
                ),
            ],
            options={"ordering": ["scheduled_for", "-created_at"]},
        ),
        migrations.CreateModel(
            name="MarketingLead",
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
                ("contact_message_id", models.PositiveBigIntegerField(blank=True, null=True, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("source", models.CharField(default="direct", max_length=60)),
                ("medium", models.CharField(blank=True, max_length=60)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("qualified", "Qualified"),
                            ("won", "Won"),
                            ("lost", "Lost"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("estimated_value", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_marketing_leads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leads",
                        to="marketing.marketingcampaign",
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lead_records",
                        to="marketing.campaignlink",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="marketing_leads",
                        to="catalog.product",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
