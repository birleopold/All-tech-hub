import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_category_parent"),
        ("commerce", "0009_order_marketing_attribution"),
    ]

    operations = [
        migrations.AddField(
            model_name="productreview",
            name="verified_order",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="verified_product_reviews",
                to="commerce.order",
                help_text="Original completed order proving that this review is from a purchase.",
            ),
        ),
        migrations.AddConstraint(
            model_name="productreview",
            constraint=models.UniqueConstraint(
                condition=models.Q(verified_order__isnull=False),
                fields=("verified_order", "product"),
                name="unique_order_verified_product_review",
            ),
        ),
    ]
