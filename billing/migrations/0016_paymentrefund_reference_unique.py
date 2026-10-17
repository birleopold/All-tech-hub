from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0015_paymentsubmission"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.UniqueConstraint(
                fields=("payment", "reference"),
                condition=~models.Q(reference=""),
                name="unique_payment_refund_reference",
            ),
        ),
    ]
