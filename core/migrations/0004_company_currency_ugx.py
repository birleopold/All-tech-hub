from django.db import migrations, models


def set_currency_ugx(apps, schema_editor):
    CompanySettings = apps.get_model("core", "CompanySettings")
    CompanySettings.objects.update(currency_code="UGX")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_phase5_fsm_audit"),
    ]

    operations = [
        migrations.RunPython(set_currency_ugx, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="companysettings",
            name="currency_code",
            field=models.CharField(default="UGX", max_length=8),
        ),
    ]
