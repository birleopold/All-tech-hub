from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SocialProfileSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("facebook_url", models.URLField(blank=True)),
                ("instagram_url", models.URLField(blank=True)),
                ("tiktok_url", models.URLField(blank=True)),
                (
                    "x_url",
                    models.URLField(blank=True, verbose_name="X / Twitter URL"),
                ),
                ("linkedin_url", models.URLField(blank=True)),
                ("youtube_url", models.URLField(blank=True)),
                (
                    "whatsapp_number",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Include the country code and digits only, for example "
                            "256700000000."
                        ),
                        max_length=32,
                    ),
                ),
                (
                    "default_share_message",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Optional short message added to product and service "
                            "sharing text."
                        ),
                        max_length=240,
                    ),
                ),
            ],
            options={
                "verbose_name": "Social media settings",
                "verbose_name_plural": "Social media settings",
            },
        ),
    ]
