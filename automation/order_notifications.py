from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.utils import timezone

from automation.models import AutomationJob


JOB_ORDER_CONFIRMATION_EMAIL = "order_confirmation_email"
JOB_ORDER_STATUS_EMAIL = "order_status_email"


def _queue_notification_job(*, key: str, job_type: str, payload: dict, when=None) -> bool:
    """Persist a notification job in the caller's current database transaction."""

    scheduled_at = when or timezone.now()
    _job, created = AutomationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "job_type": job_type,
            "payload": payload,
            "scheduled_for": scheduled_at,
            "next_attempt_at": scheduled_at,
            "max_attempts": max(
                1,
                int(getattr(settings, "AUTOMATION_JOB_MAX_ATTEMPTS", 5)),
            ),
        },
    )
    return created


def queue_order_confirmation_email(order_id: int, *, when=None) -> bool:
    order_id = int(order_id)
    return _queue_notification_job(
        key=f"order-confirmation:{order_id}",
        job_type=JOB_ORDER_CONFIRMATION_EMAIL,
        payload={"order_id": order_id},
        when=when,
    )


def queue_order_status_email(event_id: int, *, when=None) -> bool:
    event_id = int(event_id)
    return _queue_notification_job(
        key=f"order-status:{event_id}",
        job_type=JOB_ORDER_STATUS_EMAIL,
        payload={"event_id": event_id},
        when=when,
    )


def _execute_notification_job(job: AutomationJob) -> dict | None:
    if job.job_type == JOB_ORDER_CONFIRMATION_EMAIL:
        from commerce.customer_messages import deliver_order_confirmation_by_id

        row = deliver_order_confirmation_by_id(int(job.payload["order_id"]))
        return {
            "sent": bool(row),
            "outbound_email_id": row.pk if row else None,
        }

    if job.job_type == JOB_ORDER_STATUS_EMAIL:
        from commerce.customer_messages import deliver_order_status_update_by_id

        row = deliver_order_status_update_by_id(int(job.payload["event_id"]))
        return {
            "sent": bool(row),
            "outbound_email_id": row.pk if row else None,
        }

    return None


def install_order_notification_executor() -> None:
    """Extend the existing durable worker without duplicating its lock/retry logic.

    The automation service predates order notifications and has a private job
    dispatcher. This explicit application extension keeps the mature claim,
    retry, stale-lock recovery and audit implementation in one place while
    allowing order events to use the same worker. The installation is idempotent
    under Django autoreload and repeated app initialisation.
    """

    from automation import services

    current = services._execute_job
    if getattr(current, "_handles_order_notifications", False):
        return

    @wraps(current)
    def execute_with_order_notifications(job: AutomationJob) -> dict:
        result = _execute_notification_job(job)
        if result is not None:
            return result
        return current(job)

    execute_with_order_notifications._handles_order_notifications = True
    services._execute_job = execute_with_order_notifications
