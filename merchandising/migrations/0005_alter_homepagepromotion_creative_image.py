from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("merchandising", "0004_homepagepromotion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="homepagepromotion",
            name="creative_image",
            field=models.ImageField(
                blank=True,
                help_text="Optional brand-approved creative. If empty, show the selected product's real photo.",
                upload_to="homepage_campaigns/%Y/%m/",
            ),
        ),
    ]
