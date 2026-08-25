import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0009_category_parent"),
        ("commerce", "0009_order_marketing_attribution"),
        ("crm", "0002_round3_features"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerFollowUp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(db_index=True, max_length=180, unique=True)),
                ("follow_up_type", models.CharField(choices=[("warranty_expiry", "Warranty expiry check-in"), ("dormant_customer", "Dormant customer follow-up")], db_index=True, max_length=24)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("in_progress", "In progress"), ("completed", "Completed"), ("dismissed", "Dismissed")], db_index=True, default="pending", max_length=16)),
                ("priority", models.CharField(choices=[("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")], default="normal", max_length=12)),
                ("due_at", models.DateTimeField(db_index=True)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("last_contacted_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_customer_followups", to=settings.AUTH_USER_MODEL)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completed_customer_followups", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retention_followups", to="crm.customer")),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retention_followups", to="commerce.order")),
                ("product_serial", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retention_followups", to="catalog.productserial")),
            ],
            options={
                "ordering": ["due_at", "-created_at"],
                "indexes": [
                    models.Index(fields=["status", "due_at"], name="retention_followup_due_idx")
                ],
            },
        ),
    ]
