"""Keep the job expense source-reference model and migration state identical.

The original JobExpense model uses a help_text on reference that was not
recorded by 0008; Django otherwise detects migration drift at release time.
This is a state-only field metadata change, preserving all stored values.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0008_jobexpense"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobexpense",
            name="reference",
            field=models.CharField(
                max_length=120,
                help_text="Unique receipt, payment, job voucher or supplier invoice reference.",
            ),
        ),
    ]
