from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from messaging.models import EmailSuppression, OutboundEmail


def email_deliverability_findings() -> dict:
    now = timezone.now()
    stale_minutes = max(
        5,
        min(1440, int(getattr(settings, "EMAIL_STALE_QUEUE_MINUTES", 15))),
    )
    stale_cutoff = now - timedelta(minutes=stale_minutes)

    stale_queued = OutboundEmail.objects.filter(
        status=OutboundEmail.STATUS_QUEUED,
        created_at__lt=stale_cutoff,
    ).count()
    sent_without_acceptance = OutboundEmail.objects.filter(
        status=OutboundEmail.STATUS_SENT,
        accepted_at__isnull=True,
    ).count()
    delivered_without_timestamp = OutboundEmail.objects.filter(
        status=OutboundEmail.STATUS_DELIVERED,
        delivered_at__isnull=True,
    ).count()
    mismatched_addresses = OutboundEmail.objects.exclude(
        normalized_to_email=""
    ).exclude(normalized_to_email=F("to_email")).count()
    active_with_release = EmailSuppression.objects.filter(
        is_active=True,
    ).filter(Q(released_at__isnull=False) | ~Q(release_reason="")).count()
    inactive_without_release = EmailSuppression.objects.filter(
        is_active=False,
        released_at__isnull=True,
    ).count()

    bounced_addresses = set(
        OutboundEmail.objects.filter(status=OutboundEmail.STATUS_BOUNCED).values_list(
            "normalized_to_email", flat=True
        )
    )
    bounced_addresses.discard("")
    protected_bounces = set(
        EmailSuppression.objects.filter(
            email_address__in=bounced_addresses,
            is_active=True,
            scope=EmailSuppression.SCOPE_ALL,
        ).values_list("email_address", flat=True)
    )
    bounced_without_suppression = len(bounced_addresses - protected_bounces)

    complaint_addresses = set(
        OutboundEmail.objects.filter(status=OutboundEmail.STATUS_COMPLAINED).values_list(
            "normalized_to_email", flat=True
        )
    )
    complaint_addresses.discard("")
    protected_complaints = set(
        EmailSuppression.objects.filter(
            email_address__in=complaint_addresses,
            is_active=True,
            scope__in=[
                EmailSuppression.SCOPE_ALL,
                EmailSuppression.SCOPE_MARKETING,
            ],
        ).values_list("email_address", flat=True)
    )
    complaints_without_suppression = len(
        complaint_addresses - protected_complaints
    )

    duplicate_provider_ids = (
        OutboundEmail.objects.exclude(provider_message_id="")
        .values("provider", "provider_message_id")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .count()
    )
    errors = sum(
        [
            stale_queued,
            sent_without_acceptance,
            delivered_without_timestamp,
            mismatched_addresses,
            active_with_release,
            inactive_without_release,
            bounced_without_suppression,
            complaints_without_suppression,
            duplicate_provider_ids,
        ]
    )
    return {
        "errors": errors,
        "outbound_count": OutboundEmail.objects.count(),
        "active_suppressions": EmailSuppression.objects.filter(is_active=True).count(),
        "stale_minutes": stale_minutes,
        "stale_queued": stale_queued,
        "sent_without_acceptance": sent_without_acceptance,
        "delivered_without_timestamp": delivered_without_timestamp,
        "mismatched_addresses": mismatched_addresses,
        "active_with_release": active_with_release,
        "inactive_without_release": inactive_without_release,
        "bounced_without_suppression": bounced_without_suppression,
        "complaints_without_suppression": complaints_without_suppression,
        "duplicate_provider_ids": duplicate_provider_ids,
    }
