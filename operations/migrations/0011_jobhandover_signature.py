from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0010_jobhandover"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobhandover",
            name="signature",
            field=models.ImageField(
                blank=True,
                help_text="Protected recipient signature captured at completed-work handover.",
                upload_to="job_signatures/handover/%Y/%m/",
            ),
        ),
    ]
