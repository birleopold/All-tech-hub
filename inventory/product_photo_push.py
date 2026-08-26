import json
import logging

from django.conf import settings

from inventory.product_photo_models import StaffPushSubscription

logger = logging.getLogger(__name__)


def send_product_photo_push(user, *, title, body, url):
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    subject = getattr(settings, "WEBPUSH_VAPID_SUBJECT", "")
    if not private_key or not subject:
        logger.warning("webpush_not_configured")
        return 0

    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for subscription in StaffPushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                subscription.delete()
            else:
                logger.exception("webpush_delivery_failed")
    return sent
