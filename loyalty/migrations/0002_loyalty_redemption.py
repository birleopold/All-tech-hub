from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="loyaltytransaction",
            name="kind",
            field=models.CharField(choices=[("earn", "Points earned"), ("adjust", "Staff adjustment"), ("reverse", "Points reversed"), ("redeem", "Points redeemed for account credit")], max_length=16),
        )
    ]
