from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("operations", "0009_alter_jobexpense_reference"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobHandover",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient_name", models.CharField(max_length=160)),
                ("method", models.CharField(choices=[
                    ("collection", "Collected at LEOSOFT"),
                    ("delivery", "Delivered to recipient"),
                ], max_length=16)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="handover", to="operations.jobcard")),
                ("recorded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_handovers_recorded", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-recorded_at", "-id"]},
        ),
    ]
