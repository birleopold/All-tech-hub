from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from messaging.deliverability import active_suppression, normalize_email, record_local_event
from messaging.models import EmailDeliveryEvent, OutboundEmail


def _send_existing_log(
    log: OutboundEmail,
    *,
    attachment_name: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    extra_headers: dict | None = None,
) -> OutboundEmail:
    normalized = normalize_email(log.to_email)
    log.normalized_to_email = normalized
    suppression = active_suppression(normalized, log.category)
    if suppression:
        log.mark_suppressed(
            f"{suppression.reason}:{suppression.scope}:suppression-{suppression.pk}"
        )
        log.save(
            update_fields=[
                "normalized_to_email",
                "status",
                "suppression_reason",
                "suppressed_at",
                "last_event_at",
                "updated_at",
            ]
        )
        record_local_event(
            log,
            EmailDeliveryEvent.TYPE_SUPPRESSED,
            metadata={
                "suppression_id": suppression.pk,
                "reason": suppression.reason,
                "scope": suppression.scope,
            },
        )
        return log

    now = timezone.now()
    log.attempt_count += 1
    log.last_attempt_at = now
    log.status = OutboundEmail.STATUS_QUEUED
    log.error = ""
    log.suppression_reason = ""
    log.suppressed_at = None
    log.save(
        update_fields=[
            "normalized_to_email",
            "attempt_count",
            "last_attempt_at",
            "status",
            "error",
            "suppression_reason",
            "suppressed_at",
            "updated_at",
        ]
    )

    headers = {
        "X-LEOSOFT-Email-ID": str(log.tracking_token),
        "X-LEOSOFT-Email-Category": log.category,
    }
    headers.update(extra_headers or {})
    try:
        msg = EmailMessage(
            subject=log.subject,
            body=log.body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[log.to_email],
            headers=headers,
        )
        if attachment_name and attachment_bytes:
            msg.attach(attachment_name, attachment_bytes, "application/pdf")
        msg.send(fail_silently=False)
        log.provider = getattr(
            settings,
            "EMAIL_DELIVERY_PROVIDER_NAME",
            "django-email-backend",
        )[:60]
        log.mark_sent()
        log.save(
            update_fields=[
                "provider",
                "status",
                "sent_at",
                "accepted_at",
                "last_event_at",
                "error",
                "suppression_reason",
                "updated_at",
            ]
        )
        record_local_event(
            log,
            EmailDeliveryEvent.TYPE_ACCEPTED,
            metadata={"backend": getattr(settings, "EMAIL_BACKEND", "")[:300]},
        )
    except Exception as exc:
        log.mark_failed(str(exc))
        log.save(
            update_fields=[
                "status",
                "error",
                "last_event_at",
                "updated_at",
            ]
        )
        record_local_event(
            log,
            EmailDeliveryEvent.TYPE_FAILED,
            metadata={"reason": str(exc)[:1000]},
        )
    return log


def send_outbound_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    created_by,
    attachment_name: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    commercial_document=None,
    job_card=None,
    category: str = OutboundEmail.CATEGORY_TRANSACTIONAL,
    idempotency_key: str | None = None,
    extra_headers: dict | None = None,
) -> OutboundEmail:
    if category not in dict(OutboundEmail.CATEGORY_CHOICES):
        category = OutboundEmail.CATEGORY_TRANSACTIONAL
    clean_key = (idempotency_key or "").strip()[:180] or None
    if clean_key:
        existing = OutboundEmail.objects.filter(idempotency_key=clean_key).first()
        if existing:
            if existing.can_retry:
                return _send_existing_log(
                    existing,
                    attachment_name=attachment_name,
                    attachment_bytes=attachment_bytes,
                    extra_headers=extra_headers,
                )
            return existing
    subject = (subject or "")[:200]
    normalized = normalize_email(to_email)
    log = OutboundEmail.objects.create(
        to_email=normalized,
        normalized_to_email=normalized,
        category=category,
        subject=subject,
        body=body,
        status=OutboundEmail.STATUS_QUEUED,
        created_by=created_by,
        commercial_document=commercial_document,
        job_card=job_card,
        idempotency_key=clean_key,
    )
    return _send_existing_log(
        log,
        attachment_name=attachment_name,
        attachment_bytes=attachment_bytes,
        extra_headers=extra_headers,
    )


def send_queued_outbound_email(log: OutboundEmail) -> OutboundEmail:
    """Send the first attempt of a new queued record with suppression checks.

    Previously attempted or uncertain deliveries cannot be sent here; manual
    retry remains governed by retry_outbound_email().
    """
    log.refresh_from_db()
    if log.status != OutboundEmail.STATUS_QUEUED or log.attempt_count:
        return log
    return _send_existing_log(log)


def retry_outbound_email(
    log: OutboundEmail,
    *,
    attachment_name: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    extra_headers: dict | None = None,
) -> OutboundEmail:
    """Retry an eligible existing email after suppression is rechecked."""
    log.refresh_from_db()
    if not log.can_retry:
        return log
    return _send_existing_log(
        log,
        attachment_name=attachment_name,
        attachment_bytes=attachment_bytes,
        extra_headers=extra_headers,
    )
