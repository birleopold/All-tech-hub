from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("growth", "0002_clear_default_merchant_brand"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.AddField(model_name="ambassadorconversion", name="approved_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="ambassadorconversion", name="approved_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ambassador_conversions_approved", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="ambassadorconversion", name="paid_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="ambassadorconversion", name="paid_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ambassador_conversions_paid", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="ambassadorconversion", name="payout_reference", field=models.CharField(blank=True, max_length=120)),
    ]
