from django.db.models.signals import post_save
from django.dispatch import receiver

from automation.models import AutomationJob, PostChannelDelivery
from automation.services import cancel_post_automation, mark_post_manually_published
from marketing.models import ScheduledPost


@receiver(post_save, sender=ScheduledPost)
def sync_post_terminal_state(sender, instance, **kwargs):
    if instance.status == ScheduledPost.STATUS_PUBLISHED:
        mark_post_manually_published(instance)
    elif instance.status == ScheduledPost.STATUS_CANCELLED:
        cancel_post_automation(instance)


@receiver(post_save, sender=AutomationJob)
def sync_job_failure_state(sender, instance, **kwargs):
    if not instance.delivery_id:
        return
    if instance.status not in {
        AutomationJob.STATUS_RETRY,
        AutomationJob.STATUS_FAILED,
    }:
        return

    delivery_status = (
        PostChannelDelivery.STATUS_RETRYING
        if instance.status == AutomationJob.STATUS_RETRY
        else PostChannelDelivery.STATUS_FAILED
    )
    PostChannelDelivery.objects.filter(pk=instance.delivery_id).update(
        status=delivery_status,
        next_attempt_at=(
            instance.next_attempt_at
            if instance.status == AutomationJob.STATUS_RETRY
            else None
        ),
        last_error=instance.last_error,
    )
    delivery = PostChannelDelivery.objects.filter(pk=instance.delivery_id).first()
    if delivery:
        from automation.services import update_plan_status

        update_plan_status(delivery.plan)
