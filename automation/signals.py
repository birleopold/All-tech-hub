from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from automation.control import record_job_event
from automation.models import (
    AutomationJob,
    AutomationJobEvent,
    AutomationRun,
    PostChannelDelivery,
)
from automation.services import cancel_post_automation, mark_post_manually_published
from core.models import StaffNotification
from marketing.models import ScheduledPost


@receiver(post_save, sender=ScheduledPost)
def sync_post_terminal_state(sender, instance, **kwargs):
    if instance.status == ScheduledPost.STATUS_PUBLISHED:
        mark_post_manually_published(instance)
    elif instance.status == ScheduledPost.STATUS_CANCELLED:
        cancel_post_automation(instance)


@receiver(pre_save, sender=AutomationJob)
def remember_job_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = sender.objects.filter(pk=instance.pk).values_list(
        "status", flat=True
    ).first()


@receiver(post_save, sender=AutomationJob)
def record_job_status_and_sync_delivery(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_status", None)
    if created or previous != instance.status:
        action_map = {
            AutomationJob.STATUS_QUEUED: AutomationJobEvent.ACTION_QUEUED,
            AutomationJob.STATUS_RUNNING: AutomationJobEvent.ACTION_CLAIMED,
            AutomationJob.STATUS_RETRY: AutomationJobEvent.ACTION_RETRY,
            AutomationJob.STATUS_SUCCEEDED: AutomationJobEvent.ACTION_SUCCEEDED,
            AutomationJob.STATUS_FAILED: AutomationJobEvent.ACTION_FAILED,
            AutomationJob.STATUS_CANCELLED: AutomationJobEvent.ACTION_CANCELLED,
        }
        action = action_map.get(instance.status)
        if action:
            message = f"Job status changed from {previous or 'new'} to {instance.status}."
            if instance.last_error:
                message = f"{message} {instance.last_error[:350]}"
            record_job_event(
                instance,
                action,
                message=message,
                metadata={
                    "previous_status": previous,
                    "attempt_count": instance.attempt_count,
                    "worker": instance.locked_by,
                },
            )

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


@receiver(pre_save, sender=AutomationRun)
def remember_run_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = sender.objects.filter(pk=instance.pk).values_list(
        "status", flat=True
    ).first()


@receiver(post_save, sender=AutomationRun)
def notify_failed_automation_run(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_status", None)
    if instance.status not in {
        AutomationRun.STATUS_FAILED,
        AutomationRun.STATUS_PARTIAL,
    }:
        return
    if not created and previous == instance.status:
        return
    user_model = get_user_model()
    recipient_ids = list(
        user_model.objects.filter(is_staff=True)
        .filter(is_superuser=True)
        .values_list("id", flat=True)
    )
    recipient_ids.extend(
        user_model.objects.filter(is_staff=True, groups__name="Manager").values_list(
            "id", flat=True
        )
    )
    recipient_ids = sorted(set(recipient_ids))
    if not recipient_ids:
        return
    message = f"Automation run {instance.pk} {instance.get_status_display().lower()}."
    if instance.error:
        message = f"{message} {instance.error[:350]}"
    link = reverse("staff_automation_control")
    StaffNotification.objects.bulk_create(
        [
            StaffNotification(
                recipient_id=user_id,
                message=message[:500],
                link=link,
            )
            for user_id in recipient_ids
        ]
    )
