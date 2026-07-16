from django import template

from automation.connectors import MetaConfig
from automation.models import AutomationJob, PostChannelDelivery

register = template.Library()


@register.simple_tag
def automation_summary():
    config = MetaConfig.load()
    return {
        "queued": AutomationJob.objects.filter(
            status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY]
        ).count(),
        "running": AutomationJob.objects.filter(
            status=AutomationJob.STATUS_RUNNING
        ).count(),
        "failed": AutomationJob.objects.filter(
            status=AutomationJob.STATUS_FAILED
        ).count(),
        "published": PostChannelDelivery.objects.filter(
            status=PostChannelDelivery.STATUS_PUBLISHED
        ).count(),
        "manual": PostChannelDelivery.objects.filter(
            status=PostChannelDelivery.STATUS_MANUAL
        ).count(),
        "facebook_connected": config.supports("facebook"),
        "instagram_connected": config.supports("instagram"),
        "meta_enabled": config.enabled,
    }
