from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0004_lead_sales_workflow"),
        ("billing", "0014_commercialdocument_payment_request_token"),
    ]

    operations = [
        migrations.AddField(model_name="marketinglead", name="last_reminded_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="marketinglead", name="escalated_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="marketinglead", name="loss_reason", field=models.CharField(blank=True, choices=[("price", "Price too high"), ("out_of_stock", "Product unavailable"), ("slow_response", "Response was too slow"), ("delivery", "Delivery did not work"), ("competitor", "Bought from a competitor"), ("no_budget", "Customer had no budget"), ("unreachable", "Customer could not be reached"), ("other", "Other reason")], max_length=20)),
        migrations.AddField(model_name="marketinglead", name="quoted_document", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_marketing_leads", to="billing.commercialdocument")),
    ]
