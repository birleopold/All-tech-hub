from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuyingGuide",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=220)),
                ("slug", models.SlugField(max_length=220, unique=True)),
                ("excerpt", models.CharField(max_length=360)),
                ("body", models.TextField()),
                ("author_name", models.CharField(default="LEOSOFT Technical Team", max_length=160)),
                ("reviewer_name", models.CharField(blank=True, max_length=160)),
                ("keywords", models.CharField(blank=True, max_length=320)),
                ("related_category_keywords", models.CharField(blank=True, max_length=320)),
                ("is_published", models.BooleanField(default=True)),
                ("published_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-published_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CommercialLandingPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=180, unique=True)),
                ("title", models.CharField(max_length=220)),
                ("eyebrow", models.CharField(blank=True, max_length=120)),
                ("meta_description", models.CharField(max_length=320)),
                ("intro", models.TextField()),
                ("buying_guidance", models.TextField(blank=True)),
                ("category_keywords", models.CharField(blank=True, help_text="Comma-separated category words such as laptop, notebook.", max_length=300)),
                ("brand", models.CharField(blank=True, max_length=120)),
                ("condition", models.CharField(blank=True, max_length=20)),
                ("search_terms", models.CharField(blank=True, help_text="Comma-separated product-name and description terms.", max_length=400)),
                ("hero_cta", models.CharField(default="Request a quotation", max_length=100)),
                ("hero_cta_url", models.CharField(default="/contact/?type=quote", max_length=240)),
                ("is_published", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "title"]},
        ),
        migrations.CreateModel(
            name="DeliveryZone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140)),
                ("areas", models.CharField(max_length=320)),
                ("fee_from", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("lead_time", models.CharField(blank=True, max_length=160)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="ProductCommerceProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("processor_family", models.CharField(blank=True, max_length=160)),
                ("processor_generation", models.CharField(blank=True, max_length=80)),
                ("ram_capacity", models.CharField(blank=True, max_length=80)),
                ("ram_type", models.CharField(blank=True, max_length=80)),
                ("storage_capacity", models.CharField(blank=True, max_length=80)),
                ("storage_type", models.CharField(blank=True, max_length=80)),
                ("screen_size", models.CharField(blank=True, max_length=80)),
                ("screen_resolution", models.CharField(blank=True, max_length=120)),
                ("touchscreen", models.BooleanField(blank=True, null=True)),
                ("graphics", models.CharField(blank=True, max_length=180)),
                ("operating_system", models.CharField(blank=True, max_length=120)),
                ("battery_health_note", models.CharField(blank=True, max_length=220)),
                ("keyboard_condition", models.CharField(blank=True, max_length=180)),
                ("charger_included", models.BooleanField(default=True)),
                ("accessories_included", models.CharField(blank=True, max_length=220)),
                ("warranty_months", models.PositiveIntegerField(default=0)),
                ("condition_notes", models.TextField(blank=True)),
                ("actual_photos", models.BooleanField(default=False, help_text="Confirm that the public gallery shows the actual unit or stock being sold.")),
                ("delivery_note", models.CharField(blank=True, max_length=240)),
                ("stock_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("price_verified_at", models.DateTimeField(blank=True, null=True)),
                ("merchant_enabled", models.BooleanField(default=False, help_text="The product is intentionally approved for Merchant Center publication.")),
                ("merchant_shipping_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("merchant_free_shipping", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="commerce_profile", to="catalog.product")),
            ],
            options={
                "verbose_name": "Product commercial profile",
                "verbose_name_plural": "Product commercial profiles",
                "ordering": ["product__name"],
            },
        ),
        migrations.CreateModel(
            name="SearchQueryInsight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(db_index=True, max_length=500)),
                ("page", models.URLField(blank=True)),
                ("clicks", models.PositiveIntegerField(default=0)),
                ("impressions", models.PositiveIntegerField(default=0)),
                ("ctr", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=7)),
                ("position", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=8)),
                ("date_start", models.DateField(blank=True, null=True)),
                ("date_end", models.DateField(blank=True, null=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-impressions", "position", "query"],
            },
        ),
        migrations.CreateModel(
            name="CommercialLandingFAQ",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.CharField(max_length=240)),
                ("answer", models.TextField()),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("page", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="faqs", to="merchandising.commerciallandingpage")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddIndex(
            model_name="searchqueryinsight",
            index=models.Index(fields=["query", "date_end"], name="merch_query_date_idx"),
        ),
    ]
