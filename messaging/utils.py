from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from messaging.models import OutboundEmail


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
) -> OutboundEmail:
    log = OutboundEmail.objects.create(
        to_email=to_email,
        subject=subject,
        body=body,
        status=OutboundEmail.STATUS_QUEUED,
        created_by=created_by,
        commercial_document=commercial_document,
        job_card=job_card,
    )
    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to_email],
        )
        if attachment_name and attachment_bytes:
            msg.attach(attachment_name, attachment_bytes, "application/pdf")
        msg.send(fail_silently=False)
        log.mark_sent()
        log.save(update_fields=["status", "sent_at"])
    except Exception as e:
        log.status = OutboundEmail.STATUS_FAILED
        log.error = str(e)
        log.sent_at = timezone.now()
        log.save(update_fields=["status", "error", "sent_at"])
    return log


def retry_outbound_email(log: OutboundEmail, *, attachment_name: Optional[str] = None, attachment_bytes: Optional[bytes] = None) -> OutboundEmail:
    """Retry sending an existing email log entry."""
    try:
        msg = EmailMessage(
            subject=log.subject,
            body=log.body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[log.to_email],
        )
        if attachment_name and attachment_bytes:
            msg.attach(attachment_name, attachment_bytes, "application/pdf")
        msg.send(fail_silently=False)
        log.mark_sent()
        log.error = ""
        log.save(update_fields=["status", "sent_at", "error"])
    except Exception as e:
        log.mark_failed(str(e))
        log.save(update_fields=["status", "sent_at", "error"])
    return log

