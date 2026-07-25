from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("merchandising", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="productcommerceprofile",
            name="identity_verified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When brand, exact model and product identifiers were checked.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productcommerceprofile",
            name="condition_verified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When new, refurbished or used condition was physically confirmed.",
                null=True,
            ),
        ),
    ]
