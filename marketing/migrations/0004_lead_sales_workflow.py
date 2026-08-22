import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0009_order_marketing_attribution"),
        ("marketing", "0003_lead_follow_up"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketinglead",
            name="request_type",
            field=models.CharField(db_index=True, default="other", max_length=20),
        ),
        migrations.AddField(
            model_name="marketinglead",
            name="priority",
            field=models.CharField(
                choices=[
                    ("low", "Low"),
                    ("normal", "Normal"),
                    ("high", "High"),
                    ("urgent", "Urgent"),
                ],
                db_index=True,
                default="normal",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="marketinglead",
            name="response_due_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="marketinglead",
            name="won_order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="won_marketing_leads",
                to="commerce.order",
            ),
        ),
    ]
