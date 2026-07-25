from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("merchandising", "0002_product_verification_dates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productcommerceprofile",
            name="charger_included",
            field=models.BooleanField(
                blank=True,
                help_text="Leave unknown until the exact charger or power adapter is checked.",
                null=True,
            ),
        ),
    ]
