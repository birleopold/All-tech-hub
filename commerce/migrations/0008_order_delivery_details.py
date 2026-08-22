from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0007_order_cancellation_reason_order_cancelled_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivery_zone_name",
            field=models.CharField(blank=True, max_length=140),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_fee",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0"), max_digits=14
            ),
        ),
    ]
