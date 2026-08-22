from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_campaigns", "0002_scheduled_campaign_operations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customercampaign",
            name="channel",
            field=models.CharField(
                choices=[
                    ("email", "Email"),
                    ("whatsapp", "WhatsApp (manual click-to-chat)"),
                ],
                default="email",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="customercampaignrecipient",
            name="email_address",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="customercampaignrecipient",
            name="phone_number",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
