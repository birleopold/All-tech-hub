from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0011_jobhandover_signature")]

    operations = [
        migrations.AddField(
            model_name="jobnote",
            name="client_operation_id",
            field=models.UUIDField(
                null=True,
                blank=True,
                unique=True,
                editable=False,
                help_text="Idempotency key for explicitly synced offline technician notes.",
            ),
        ),
    ]
