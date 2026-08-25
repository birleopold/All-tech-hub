import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0014_commercialdocument_payment_request_token"),
        ("reliability", "0003_provider_reference_uniqueness"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("method", models.CharField(choices=[("cash", "Cash"), ("card", "Card"), ("transfer", "Bank transfer"), ("mobile_money", "Mobile Money"), ("cheque", "Cheque"), ("other", "Other")], max_length=20)),
                ("reference", models.CharField(db_index=True, max_length=120)),
                ("payer_name", models.CharField(blank=True, max_length=120)),
                ("payer_email", models.EmailField(blank=True, max_length=254)),
                ("payer_phone", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(choices=[("pending", "Awaiting verification"), ("verified", "Verified"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=16)),
                ("review_note", models.CharField(blank=True, max_length=255)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_submissions", to="billing.commercialdocument")),
                ("payment_attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="document_submissions", to="reliability.paymentattempt")),
                ("recorded_payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_submissions", to="billing.documentpayment")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_submissions_reviewed", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="positive_payment_submission_amount"),
                    models.UniqueConstraint(fields=("method", "reference"), name="unique_manual_payment_submission_reference"),
                ],
            },
        ),
    ]
