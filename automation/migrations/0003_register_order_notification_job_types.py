from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0002_control_runs_job_events"),
    ]

    operations = [
        migrations.AlterField(
            model_name="automationjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("social_post", "Social post"),
                    ("saved_cart_email", "Saved-cart email"),
                    ("stock_alert_email", "Stock alert email"),
                    ("order_confirmation_email", "Order confirmation email"),
                    ("order_status_email", "Order status email"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
