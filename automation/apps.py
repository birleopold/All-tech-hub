from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "automation"

    def ready(self):
        from automation import signals  # noqa: F401
        from automation.order_notifications import install_order_notification_executor

        install_order_notification_executor()
