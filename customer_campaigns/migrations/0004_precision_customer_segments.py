from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("customer_campaigns", "0003_whatsapp_campaigns"), ("catalog", "0009_category_parent")]

    operations = [
        migrations.AlterField(model_name="customercampaign", name="segment", field=models.CharField(choices=[("all", "All eligible customers"), ("repeat", "Repeat customers"), ("recent", "Ordered in the last 90 days"), ("dormant", "No order for at least 90 days"), ("high_value", "High-value customers"), ("new", "Customers added in the last 30 days"), ("no_purchase", "Customers without a completed purchase"), ("product_interest", "Customers who enquired about a product")], default="all", max_length=16)),
        migrations.AddField(model_name="customercampaign", name="target_product", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="targeted_customer_campaigns", to="catalog.product")),
        migrations.AddField(model_name="customercampaign", name="minimum_customer_spend", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField(model_name="customercampaign", name="location_query", field=models.CharField(blank=True, max_length=120)),
    ]
