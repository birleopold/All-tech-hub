from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0015_paymentsubmission"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentrefund",
            name="idempotency_key",
            field=models.CharField(
                editable=False, max_length=200, null=True, unique=True
            ),
        ),
    ]
