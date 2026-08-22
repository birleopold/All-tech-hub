import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_category_parent"),
        ("core", "0011_companysettings_authorised_signatory_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contact_enquiries",
                to="catalog.product",
            ),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="request_type",
            field=models.CharField(db_index=True, default="other", max_length=20),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="related_product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="support_tickets",
                to="catalog.product",
            ),
        ),
    ]
