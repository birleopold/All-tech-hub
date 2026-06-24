from django.db import migrations, models
import django.db.models.deletion


def copy_customer_details(apps, schema_editor):
    CommercialDocument = apps.get_model("billing", "CommercialDocument")
    for document in CommercialDocument.objects.select_related("customer").iterator():
        customer = document.customer
        document.customer_name = customer.name
        document.customer_company = customer.company_name
        document.customer_email = customer.email
        document.customer_phone = customer.phone
        document.customer_tax_reference = customer.tax_reference
        document.save(
            update_fields=[
                "customer_name",
                "customer_company",
                "customer_email",
                "customer_phone",
                "customer_tax_reference",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0008_documentpayment_reconciled_and_more")]

    operations = [
        migrations.AlterField(
            model_name="commercialdocument",
            name="customer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="documents",
                to="crm.customer",
            ),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_company",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_name",
            field=models.CharField(
                blank=True,
                help_text="Customer name as printed on this document.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_phone",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="commercialdocument",
            name="customer_tax_reference",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.RunPython(copy_customer_details, migrations.RunPython.noop),
    ]
