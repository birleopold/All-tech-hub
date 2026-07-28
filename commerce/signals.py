from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from automation.order_notifications import (
    queue_order_confirmation_email,
    queue_order_status_email,
)
from commerce.models import Order, OrderStatusEvent
from commerce.retention import send_order_review_request_by_id
from loyalty.services import award_completed_order_points_by_id


@receiver(post_save, sender=Order)
def queue_customer_order_confirmation_email(sender, instance, created, **kwargs):
    if created:
        # This job row is written inside the same database transaction as the
        # order, so a rolled-back checkout cannot leave an orphan notification.
        queue_order_confirmation_email(instance.pk)


@receiver(post_save, sender=OrderStatusEvent)
def queue_customer_order_status_email(sender, instance, created, **kwargs):
    if not created:
        return

    if instance.visible_to_customer:
        # Persist the durable job with the status event. The worker handles SMTP,
        # retries, stale locks and final failure reporting after commit.
        queue_order_status_email(instance.pk)

    if instance.to_status in {Order.STATUS_DELIVERED, Order.STATUS_FULFILLED}:
        order_id = instance.order_id
        if instance.visible_to_customer:
            transaction.on_commit(lambda: send_order_review_request_by_id(order_id))
        transaction.on_commit(
            lambda: award_completed_order_points_by_id(order_id),
            robust=True,
        )
