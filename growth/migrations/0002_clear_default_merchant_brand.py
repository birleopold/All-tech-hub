from django.db import migrations


def create_safe_growth_settings(apps, schema_editor):
    GrowthSettings = apps.get_model("growth", "GrowthSettings")
    GrowthSettings.objects.update_or_create(
        pk=1,
        defaults={"merchant_default_brand": ""},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("growth", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_safe_growth_settings,
            migrations.RunPython.noop,
        ),
    ]
