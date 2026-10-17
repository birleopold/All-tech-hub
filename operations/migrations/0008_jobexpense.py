from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0007_round3_features"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="JobExpense",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID",
                )),
                ("category", models.CharField(
                    max_length=24, choices=[
                        ("parts", "Direct parts purchase"),
                        ("labour", "Actual labour cost"),
                        ("transport", "Transport and field travel"),
                        ("subcontractor", "Subcontractor / external service"),
                        ("other", "Other direct expense"),
                    ],
                )),
                ("description", models.CharField(max_length=255)),
                ("reference", models.CharField(max_length=120)),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="expenses", to="operations.jobcard",
                )),
                ("recorded_by", models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="job_expenses_recorded",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-recorded_at", "-pk"]},
        ),
        migrations.AddConstraint(
            model_name="jobexpense",
            constraint=models.UniqueConstraint(
                fields=("job", "reference"),
                name="unique_expense_reference_per_job",
            ),
        ),
        migrations.AddConstraint(
            model_name="jobexpense",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="job_expense_amount_positive",
            ),
        ),
    ]
