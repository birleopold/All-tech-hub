from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0002_deliverability_suppression"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emaildeliveryevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("accepted", "Accepted"),
                    ("delivered", "Delivered"),
                    ("soft_bounce", "Soft bounce"),
                    ("hard_bounce", "Hard bounce"),
                    ("complaint", "Complaint"),
                    ("suppressed", "Suppressed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
