from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_productreview_verified_order")]

    operations = [
        migrations.AddField(
            model_name="category", name="seo_title",
            field=models.CharField(
                blank=True, max_length=90,
                help_text="Optional Google search title; leave blank for the tailored Uganda category title.",
            ),
        ),
        migrations.AddField(
            model_name="category", name="seo_description",
            field=models.CharField(
                blank=True, max_length=240,
                help_text="Optional search description. Use verified facts, not unconfirmed stock or delivery promises.",
            ),
        ),
        migrations.AddField(
            model_name="category", name="seo_heading",
            field=models.CharField(
                blank=True, max_length=120,
                help_text="Optional short on-page heading; keep the category easy to shop.",
            ),
        ),
    ]
