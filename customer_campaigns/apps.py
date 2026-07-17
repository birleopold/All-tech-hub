from django.apps import AppConfig


class CustomerCampaignsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customer_campaigns"
    verbose_name = "Customer campaign execution"

    def ready(self):
        from customer_campaigns import signals  # noqa: F401
