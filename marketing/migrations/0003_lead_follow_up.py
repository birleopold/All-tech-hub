from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0002_marketing_automation"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketinglead",
            name="first_contacted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="marketinglead",
            name="next_follow_up_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="marketinglead",
            name="won_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
