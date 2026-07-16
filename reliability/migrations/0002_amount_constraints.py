from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reliability", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_attempt_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_refund_amount_positive",
            ),
        ),
    ]
