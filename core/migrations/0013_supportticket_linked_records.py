import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_product_linked_enquiries"),
        ("operations", "0007_round3_features"),
        ("billing", "0015_paymentsubmission"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportticket",
            name="related_job",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="support_tickets", to="operations.jobcard",
            ),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="related_document",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="support_tickets", to="billing.commercialdocument",
            ),
        ),
    ]
