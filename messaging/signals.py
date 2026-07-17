from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from customer_campaigns.models import CustomerCampaignRecipient
from messaging.deliverability import normalize_email
from messaging.models import OutboundEmail


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
