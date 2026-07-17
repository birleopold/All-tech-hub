from __future__ import annotations

from automation.connectors import ConnectorError
from automation.models import AutomationJob
from growth.models import SavedCart, StockAlertSubscription
from growth.services import (
    send_saved_cart_message,
    send_stock_alert_message,
    stock_alert_reason,
)
from messaging.models import OutboundEmail


def _accepted(status: str) -> bool:
    return status in {
        OutboundEmail.STATUS_SENT,
        OutboundEmail.STATUS_DELIVERED,
    }


def execute_email_automation_job(job: AutomationJob) -> dict:
    if job.job_type == AutomationJob.TYPE_SAVED_CART_EMAIL:
        saved = SavedCart.objects.get(pk=int(job.payload["saved_cart_id"]))
        reminder_number = int(job.payload["reminder_number"])
        if saved.status != SavedCart.STATUS_ACTIVE:
            return {"skipped": True, "reason": "Cart is no longer active."}
        if reminder_number == 1 and saved.first_reminder_sent_at:
            return {"skipped": True, "reason": "First reminder was already handled."}
        if reminder_number == 2 and saved.second_reminder_sent_at:
            return {"skipped": True, "reason": "Second reminder was already handled."}

        log = send_saved_cart_message(saved, reminder_number=reminder_number)
        if log.status == OutboundEmail.STATUS_SUPPRESSED:
            _mark_saved_cart_reminder_handled(saved, reminder_number)
            return {
                "skipped": True,
                "reason": "Recipient is actively suppressed.",
                "outbound_email_id": log.pk,
            }
        if not _accepted(log.status):
            raise ConnectorError(
                log.error or "Saved-cart email was not accepted by the email backend.",
                retryable=log.status in {
                    OutboundEmail.STATUS_FAILED,
                    OutboundEmail.STATUS_SOFT_BOUNCED,
                },
            )
        _mark_saved_cart_reminder_handled(saved, reminder_number)
        return {
            "sent": True,
            "reminder_number": reminder_number,
            "outbound_email_id": log.pk,
            "tracking_token": str(log.tracking_token),
        }

    if job.job_type == AutomationJob.TYPE_STOCK_ALERT_EMAIL:
        subscription = StockAlertSubscription.objects.select_related(
            "product", "product__category"
        ).get(pk=int(job.payload["subscription_id"]))
        triggered, reason = stock_alert_reason(subscription)
        if not subscription.is_active or not triggered:
            return {"skipped": True, "reason": "Alert condition is no longer active."}

        log = send_stock_alert_message(subscription, reason=reason)
        if log.status == OutboundEmail.STATUS_SUPPRESSED:
            _close_stock_alert(subscription)
            return {
                "skipped": True,
                "reason": "Recipient is actively suppressed.",
                "outbound_email_id": log.pk,
            }
        if not _accepted(log.status):
            raise ConnectorError(
                log.error or "Stock-alert email was not accepted by the email backend.",
                retryable=log.status in {
                    OutboundEmail.STATUS_FAILED,
                    OutboundEmail.STATUS_SOFT_BOUNCED,
                },
            )
        _close_stock_alert(subscription)
        return {
            "sent": True,
            "outbound_email_id": log.pk,
            "tracking_token": str(log.tracking_token),
        }

    raise ConnectorError("Unknown email automation job type.", retryable=False)


def _mark_saved_cart_reminder_handled(saved: SavedCart, reminder_number: int) -> None:
    from django.utils import timezone

    now = timezone.now()
    if reminder_number == 1:
        saved.first_reminder_sent_at = now
        saved.save(update_fields=["first_reminder_sent_at", "updated_at"])
    else:
        saved.second_reminder_sent_at = now
        saved.save(update_fields=["second_reminder_sent_at", "updated_at"])


def _close_stock_alert(subscription: StockAlertSubscription) -> None:
    from django.utils import timezone

    subscription.is_active = False
    subscription.notified_at = timezone.now()
    subscription.save(update_fields=["is_active", "notified_at"])
