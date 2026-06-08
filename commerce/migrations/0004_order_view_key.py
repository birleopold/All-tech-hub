# Generated manually: unique UUIDs for existing orders, then enforce NOT NULL + UNIQUE.

import uuid

from django.db import migrations, models


def fill_view_keys(apps, schema_editor):
    Order = apps.get_model("commerce", "Order")
    for row in Order.objects.filter(view_key__isnull=True).iterator():
        row.view_key = uuid.uuid4()
        row.save(update_fields=["view_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("commerce", "0003_phase3_portal_ops"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="view_key",
            field=models.UUIDField(
                db_index=True,
                editable=False,
                help_text="Secret fragment for the public order receipt URL (not guessable from the reference).",
                null=True,
            ),
        ),
        migrations.RunPython(fill_view_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="view_key",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text="Secret fragment for the public order receipt URL (not guessable from the reference).",
                unique=True,
            ),
        ),
    ]
