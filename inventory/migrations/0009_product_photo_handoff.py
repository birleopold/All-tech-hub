from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import inventory.product_photo_models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0008_alter_stockmovement_movement_type"),
        ("catalog", "0002_phase2_gallery_variants"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffPushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(max_length=1000, unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-last_used_at",)},
        ),
        migrations.CreateModel(
            name="ProductPhotoSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(db_index=True, editable=False, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True, default=inventory.product_photo_models.default_photo_session_expiry)),
                ("last_upload_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_photo_sessions", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photo_sessions", to="catalog.product")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
