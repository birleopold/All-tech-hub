from django.db.models.signals import post_save
from django.dispatch import receiver

from automation.services import cancel_post_automation, mark_post_manually_published
from marketing.models import ScheduledPost


@receiver(post_save, sender=ScheduledPost)
def sync_post_terminal_state(sender, instance, **kwargs):
    if instance.status == ScheduledPost.STATUS_PUBLISHED:
        mark_post_manually_published(instance)
    elif instance.status == ScheduledPost.STATUS_CANCELLED:
        cancel_post_automation(instance)
