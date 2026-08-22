import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0008_order_delivery_details"),
        ("marketing", "0003_lead_follow_up"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="marketing_link",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attributed_orders",
                to="marketing.campaignlink",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="marketing_source",
            field=models.CharField(blank=True, db_index=True, max_length=60),
        ),
        migrations.AddField(
            model_name="order",
            name="marketing_medium",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="order",
            name="marketing_campaign",
            field=models.CharField(blank=True, db_index=True, max_length=200),
        ),
        migrations.AddField(
            model_name="order",
            name="marketing_content",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="order",
            name="marketing_attributed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
