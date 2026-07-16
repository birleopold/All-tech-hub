from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reliability", "0002_amount_constraints"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.UniqueConstraint(
                fields=("provider", "external_reference"),
                condition=~models.Q(external_reference=""),
                name="unique_provider_payment_reference",
            ),
        ),
    ]
