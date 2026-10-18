import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0010_productreview_verified_order"),
        ("merchandising", "0003_charger_confirmation"),
    ]
    operations = [
        migrations.CreateModel(
            name="HomepagePromotion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slot", models.CharField(choices=[("hero", "Main hero"), ("side_top", "Upper promotion"), ("side_bottom", "Lower promotion")], db_index=True, max_length=16)),
                ("headline", models.CharField(max_length=90)),
                ("eyebrow", models.CharField(blank=True, max_length=48)),
                ("supporting_text", models.CharField(blank=True, max_length=135)),
                ("button_label", models.CharField(default="Explore products", max_length=32)),
                ("link_path", models.CharField(default="/catalog/", help_text="Internal path only (for example /catalog/ or /catalog/services/).", max_length=250)),
                ("creative_image", models.ImageField(blank=True, upload_to="homepage_campaigns/%Y/%m/")),
                ("image_alt", models.CharField(blank=True, max_length=140)),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=False)),
                ("priority", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(blank=True, help_text="Optional real product to illustrate the campaign.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="homepage_promotions", to="catalog.product")),
            ],
            options={"ordering": ["slot", "-priority", "-updated_at", "-pk"]},
        ),
    ]
