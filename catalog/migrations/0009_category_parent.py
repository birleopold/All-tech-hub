# Generated manually for hierarchical product categories.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_product_product_stock_nonnegative_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="Leave blank for a main menu category.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subcategories",
                to="catalog.category",
            ),
        ),
    ]
