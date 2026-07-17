from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.audit import log_audit_event
from messaging.models import EmailDeliveryEvent, EmailSuppression, OutboundEmail


class DeliverabilityError(Exception):
    pass


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _clean_metadata(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key, item in list(value.items())[:30]:
        name = str(key)[:80]
        if item is None or isinstance(item, (bool, int, float)):
            cleaned[name] = item
        elif isinstance(item, str):
            cleaned[name] = item[:1000]
        elif isinstance(item, (list, tuple)):
            cleaned[name] = [str(entry)[:300] for entry in list(item)[:20]]
        else:
            cleaned[name] = str(item)[:1000]
    return cleaned


def _event_time(value) -> timezone.datetime:
    if isinstance(value, timezone.datetime):
        occurred_at = value
    elif isinstance(value, str):
        occurred_at = parse_datetime(value)
    else:
        occurred_at = None
    if occurred_at is None:
        occurred_at = timezone.now()
    if timezone.is_naive(occurred_at):
        occurred_at = timezone.make_aware(occurred_at, timezone.get_current_timezone())
    return occurred_at


def suppression_applies(suppression: EmailSuppression, category: str) -> bool:
    if not suppression.is_active:
        return False
    if suppression.scope == EmailSuppression.SCOPE_ALL:
        return True
    return category == OutboundEmail.CATEGORY_MARKETING


def active_suppression(email_address: str, category: str) -> EmailSuppression | None:
    normalized = normalize_email(email_address)
    if not normalized:
        return None
    row = EmailSuppression.objects.filter(
        email_address=normalized,
        is_active=True,
    ).first()
    return row if row and suppression_applies(row, category) else None


@transaction.atomic
def upsert_suppression(
    *,
    email_address: str,
    reason: str,
    scope: str,
    source: str,
    actor=None,
    details: dict | None = None,
    occurred_at=None,
) -> EmailSuppression:
    normalized = normalize_email(email_address)
    if not normalized:
        raise DeliverabilityError("A valid email address is required for suppression.")
    if reason not in dict(EmailSuppression.REASON_CHOICES):
        raise DeliverabilityError("Unknown suppression reason.")
    if scope not in dict(EmailSuppression.SCOPE_CHOICES):
        raise DeliverabilityError("Unknown suppression scope.")
    if source not in dict(EmailSuppression.SOURCE_CHOICES):
        raise DeliverabilityError("Unknown suppression source.")

    seen_at = _event_time(occurred_at)
    suppression = EmailSuppression.objects.select_for_update().filter(
        email_address=normalized
    ).first()
    if suppression is None:
        suppression = EmailSuppression.objects.create(
            email_address=normalized,
            scope=scope,
            reason=reason,
            source=source,
            details=_clean_metadata(details),
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            created_by=actor,
        )
    else:
        suppression.is_active = True
        if scope == EmailSuppression.SCOPE_ALL:
            suppression.scope = EmailSuppression.SCOPE_ALL
        suppression.reason = reason
        suppression.source = source
        suppression.event_count += 1
        suppression.last_seen_at = max(suppression.last_seen_at, seen_at)
        suppression.details = _clean_metadata(details)
        suppression.released_by = None
        suppression.released_at = None
        suppression.release_reason = ""
        if actor and not suppression.created_by_id:
            suppression.created_by = actor
        suppression.save(
            update_fields=[
                "is_active",
                "scope",
                "reason",
                "source",
                "event_count",
                "last_seen_at",
                "details",
                "released_by",
                "released_at",
                "release_reason",
                "created_by",
                "updated_at",
            ]
        )
    log_audit_event(
        actor=actor,
        verb="messaging.email_suppressed",
        summary=(
            f"Email suppression active for {normalized}: "
            f"{suppression.get_reason_display()} ({suppression.get_scope_display()})."
        ),
        target=suppression,
    )
    return suppression


@transaction.atomic
def release_suppression(
    suppression: EmailSuppression,
    *,
    user,
    reason: str,
) -> EmailSuppression:
    suppression = EmailSuppression.objects.select_for_update().get(pk=suppression.pk)
    if not suppression.is_active:
        raise DeliverabilityError("This suppression is already inactive.")
    reason = (reason or "").strip()
    if len(reason) < 8:
        raise DeliverabilityError("Record a clear release reason of at least 8 characters.")
    suppression.is_active = False
    suppression.released_by = user
    suppression.released_at = timezone.now()
    suppression.release_reason = reason[:300]
    suppression.save(
        update_fields=[
            "is_active",
            "released_by",
            "released_at",
            "release_reason",
            "updated_at",
        ]
    )
    log_audit_event(
        actor=user,
        verb="messaging.email_suppression_released",
        summary=f"Released email suppression for {suppression.email_address}: {reason[:300]}",
        target=suppression,
    )
    return suppression


def _resolve_outbound(payload: dict) -> OutboundEmail | None:
    tracking_token = payload.get("tracking_token")
    if tracking_token:
        try:
            parsed = UUID(str(tracking_token))
        except (TypeError, ValueError, AttributeError) as exc:
            raise DeliverabilityError("Invalid tracking token.") from exc
        row = OutboundEmail.objects.filter(tracking_token=parsed).first()
        if row:
            return row
    outbound_id = payload.get("outbound_email_id")
    if outbound_id not in (None, ""):
        try:
            row = OutboundEmail.objects.filter(pk=int(outbound_id)).first()
        except (TypeError, ValueError) as exc:
            raise DeliverabilityError("Invalid outbound email ID.") from exc
        if row:
            return row
    provider_message_id = str(payload.get("provider_message_id") or "").strip()
    if provider_message_id:
        return OutboundEmail.objects.filter(
            provider_message_id=provider_message_id
        ).order_by("-created_at").first()
    return None


def _payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _update_campaign_recipient(outbound: OutboundEmail, event_type: str, message: str) -> None:
    try:
        from customer_campaigns.models import CustomerCampaignRecipient
        from customer_campaigns.services import refresh_campaign_counts
    except ImportError:
        return
    recipients = list(
        outbound.customer_campaign_recipients.select_related("campaign").all()
    )
    for recipient in recipients:
        if event_type in {
            EmailDeliveryEvent.TYPE_HARD_BOUNCE,
            EmailDeliveryEvent.TYPE_SOFT_BOUNCE,
        }:
            recipient.status = CustomerCampaignRecipient.STATUS_FAILED
            recipient.suppression_reason = message[:160]
            recipient.save(
                update_fields=["status", "suppression_reason", "updated_at"]
            )
        elif event_type in {
            EmailDeliveryEvent.TYPE_COMPLAINT,
            EmailDeliveryEvent.TYPE_SUPPRESSED,
        }:
            recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
            recipient.suppression_reason = message[:160]
            recipient.save(
                update_fields=["status", "suppression_reason", "updated_at"]
            )
        refresh_campaign_counts(recipient.campaign)


@transaction.atomic
def record_delivery_event(payload: dict) -> tuple[EmailDeliveryEvent, bool]:
    if not isinstance(payload, dict):
        raise DeliverabilityError("Delivery event payload must be a JSON object.")
    event_key = str(payload.get("event_id") or payload.get("event_key") or "").strip()
    if not event_key or len(event_key) > 240:
        raise DeliverabilityError("A provider event ID is required.")
    existing = EmailDeliveryEvent.objects.filter(event_key=event_key).first()
    if existing:
        return existing, False

    event_type = str(payload.get("event_type") or "").strip()
    if event_type not in dict(EmailDeliveryEvent.TYPE_CHOICES):
        raise DeliverabilityError("Unknown delivery event type.")
    provider = str(payload.get("provider") or "").strip()[:60]
    provider_message_id = str(payload.get("provider_message_id") or "").strip()[:240]
    occurred_at = _event_time(payload.get("occurred_at"))
    metadata = _clean_metadata(payload.get("metadata"))

    outbound = _resolve_outbound(payload)
    if outbound:
        outbound = OutboundEmail.objects.select_for_update().get(pk=outbound.pk)
    email_address = normalize_email(
        payload.get("email") or (outbound.normalized_to_email if outbound else "")
    )
    if not email_address:
        raise DeliverabilityError("The delivery event does not identify an email address.")
    if outbound and outbound.normalized_to_email and email_address != outbound.normalized_to_email:
        raise DeliverabilityError("Delivery event email does not match the outbound record.")

    event = EmailDeliveryEvent.objects.create(
        event_key=event_key,
        outbound_email=outbound,
        email_address=email_address,
        event_type=event_type,
        provider=provider,
        provider_message_id=provider_message_id,
        occurred_at=occurred_at,
        payload_hash=_payload_hash(payload),
        metadata=metadata,
    )

    diagnostic = str(
        metadata.get("diagnostic")
        or metadata.get("reason")
        or event.get_event_type_display()
    )[:4000]
    if outbound:
        if provider:
            outbound.provider = provider
        if provider_message_id:
            outbound.provider_message_id = provider_message_id
        outbound.last_event_at = occurred_at
        if event_type == EmailDeliveryEvent.TYPE_ACCEPTED:
            outbound.status = OutboundEmail.STATUS_SENT
            outbound.accepted_at = outbound.accepted_at or occurred_at
            outbound.sent_at = outbound.sent_at or occurred_at
            outbound.error = ""
        elif event_type == EmailDeliveryEvent.TYPE_DELIVERED:
            outbound.status = OutboundEmail.STATUS_DELIVERED
            outbound.delivered_at = occurred_at
            outbound.accepted_at = outbound.accepted_at or occurred_at
            outbound.sent_at = outbound.sent_at or occurred_at
            outbound.error = ""
        elif event_type == EmailDeliveryEvent.TYPE_SOFT_BOUNCE:
            outbound.status = OutboundEmail.STATUS_SOFT_BOUNCED
            outbound.bounced_at = occurred_at
            outbound.error = diagnostic
        elif event_type == EmailDeliveryEvent.TYPE_HARD_BOUNCE:
            outbound.status = OutboundEmail.STATUS_BOUNCED
            outbound.bounced_at = occurred_at
            outbound.error = diagnostic
        elif event_type == EmailDeliveryEvent.TYPE_COMPLAINT:
            outbound.status = OutboundEmail.STATUS_COMPLAINED
            outbound.complained_at = occurred_at
            outbound.error = diagnostic
        elif event_type == EmailDeliveryEvent.TYPE_SUPPRESSED:
            outbound.mark_suppressed(diagnostic)
        outbound.save()

    if event_type == EmailDeliveryEvent.TYPE_HARD_BOUNCE:
        upsert_suppression(
            email_address=email_address,
            reason=EmailSuppression.REASON_HARD_BOUNCE,
            scope=EmailSuppression.SCOPE_ALL,
            source=EmailSuppression.SOURCE_PROVIDER,
            details=metadata,
            occurred_at=occurred_at,
        )
    elif event_type == EmailDeliveryEvent.TYPE_COMPLAINT:
        upsert_suppression(
            email_address=email_address,
            reason=EmailSuppression.REASON_COMPLAINT,
            scope=EmailSuppression.SCOPE_MARKETING,
            source=EmailSuppression.SOURCE_PROVIDER,
            details=metadata,
            occurred_at=occurred_at,
        )
    elif event_type == EmailDeliveryEvent.TYPE_SOFT_BOUNCE:
        threshold = max(
            2,
            min(
                20,
                int(getattr(settings, "EMAIL_SOFT_BOUNCE_SUPPRESSION_THRESHOLD", 3)),
            ),
        )
        window_days = max(
            1,
            min(90, int(getattr(settings, "EMAIL_SOFT_BOUNCE_WINDOW_DAYS", 30))),
        )
        soft_count = EmailDeliveryEvent.objects.filter(
            email_address=email_address,
            event_type=EmailDeliveryEvent.TYPE_SOFT_BOUNCE,
            occurred_at__gte=occurred_at - timedelta(days=window_days),
        ).count()
        if soft_count >= threshold:
            upsert_suppression(
                email_address=email_address,
                reason=EmailSuppression.REASON_REPEATED_SOFT_BOUNCE,
                scope=EmailSuppression.SCOPE_ALL,
                source=EmailSuppression.SOURCE_SYSTEM,
                details={"soft_bounce_count": soft_count, "window_days": window_days},
                occurred_at=occurred_at,
            )

    if outbound:
        _update_campaign_recipient(outbound, event_type, diagnostic)
    return event, True


def record_local_event(
    outbound: OutboundEmail,
    event_type: str,
    *,
    metadata: dict | None = None,
) -> EmailDeliveryEvent:
    event, _created = record_delivery_event(
        {
            "event_id": (
                f"local:{event_type}:{outbound.tracking_token}:"
                f"{max(1, outbound.attempt_count)}"
            ),
            "event_type": event_type,
            "provider": outbound.provider or "django-email-backend",
            "tracking_token": str(outbound.tracking_token),
            "email": outbound.normalized_to_email or outbound.to_email,
            "occurred_at": timezone.now().isoformat(),
            "metadata": metadata or {},
        }
    )
    return event
