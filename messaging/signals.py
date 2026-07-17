from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from customer_campaigns.models import CustomerCampaignRecipient
from messaging.deliverability import normalize_email
from messaging.models import EmailDeliveryEvent, OutboundEmail


@receiver(pre_save, sender=OutboundEmail)
def normalize_outbound_email(sender, instance, **kwargs):
    instance.to_email = normalize_email(instance.to_email)
    instance.normalized_to_email = instance.to_email


@receiver(post_save, sender=CustomerCampaignRecipient)
def classify_campaign_outbound_email(sender, instance, **kwargs):
    if not instance.outbound_email_id:
        return
    OutboundEmail.objects.filter(pk=instance.outbound_email_id).exclude(
        category=OutboundEmail.CATEGORY_MARKETING
    ).update(
        category=OutboundEmail.CATEGORY_MARKETING,
        normalized_to_email=normalize_email(instance.email_address),
    )


@receiver(post_save, sender=EmailDeliveryEvent)
def reconcile_immediate_campaign_suppression(sender, instance, created, **kwargs):
    if (
        not created
        or instance.event_type != EmailDeliveryEvent.TYPE_SUPPRESSED
        or not instance.outbound_email_id
    ):
        return
    from messaging.deliverability import _update_campaign_recipient

    _update_campaign_recipient(
        instance.outbound_email,
        instance.event_type,
        str(instance.metadata.get("reason") or "address_suppressed"),
    )
