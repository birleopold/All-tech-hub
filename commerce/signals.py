from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from commerce.customer_messages import send_order_status_update_by_id
from commerce.models import OrderStatusEvent


@receiver(post_save, sender=OrderStatusEvent)
def queue_customer_order_status_email(sender, instance, created, **kwargs):
    if not created or not instance.visible_to_customer:
        return
    event_id = instance.pk
    transaction.on_commit(lambda: send_order_status_update_by_id(event_id))
