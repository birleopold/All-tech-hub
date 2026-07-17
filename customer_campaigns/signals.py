from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from core.models import StaffNotification
from customer_campaigns.models import CampaignAutomationEvent


CRITICAL_ACTIONS = {
    CampaignAutomationEvent.ACTION_PAUSED,
    CampaignAutomationEvent.ACTION_EXPIRED,
    CampaignAutomationEvent.ACTION_COMPLETED,
    CampaignAutomationEvent.ACTION_FAILED,
}


@receiver(post_save, sender=CampaignAutomationEvent)
def notify_campaign_staff(sender, instance, created, **kwargs):
    if not created or instance.action not in CRITICAL_ACTIONS:
        return
    campaign = instance.campaign
    recipient_ids = {
        user_id
        for user_id in [
            campaign.created_by_id,
            campaign.prepared_by_id,
            campaign.approved_by_id,
            campaign.scheduled_by_id,
        ]
        if user_id
    }
    if instance.actor_id:
        recipient_ids.discard(instance.actor_id)
    if not recipient_ids:
        return
    action_label = instance.get_action_display()
    message = f"Campaign {campaign.name}: {action_label}."
    if instance.message:
        message = f"{message} {instance.message}"
    link = reverse("staff_customer_campaign_detail", kwargs={"pk": campaign.pk})
    StaffNotification.objects.bulk_create(
        [
            StaffNotification(
                recipient_id=user_id,
                message=message[:500],
                link=link,
            )
            for user_id in sorted(recipient_ids)
        ]
    )
