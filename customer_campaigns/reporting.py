from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from customer_campaigns.models import CustomerCampaign, CustomerCampaignRecipient
from loyalty.models import CustomerMarketingPreference, MarketingConsentEvent
from messaging.models import OutboundEmail


def campaign_integrity_findings() -> dict:
    stale_cutoff = timezone.now() - timedelta(minutes=30)
    approved_statuses = [
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SENDING,
        CustomerCampaign.STATUS_COMPLETED,
    ]
    approved_missing_record = CustomerCampaign.objects.filter(
        status__in=approved_statuses
    ).filter(Q(approved_by__isnull=True) | Q(approved_at__isnull=True)).count()

    self_approved = 0
    if getattr(settings, "CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER", True):
        self_approved = CustomerCampaign.objects.filter(
            status__in=approved_statuses,
            approved_by__isnull=False,
        ).filter(
            Q(approved_by_id=F("created_by_id"))
            | Q(approved_by_id=F("prepared_by_id"))
        ).count()

    stale_processing = CustomerCampaignRecipient.objects.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
        attempted_at__lt=stale_cutoff,
    ).count()
    completed_with_unfinished = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_COMPLETED,
        recipients__status__in=[
            CustomerCampaignRecipient.STATUS_PENDING,
            CustomerCampaignRecipient.STATUS_PROCESSING,
        ],
    ).distinct().count()
    sent_without_success_log = CustomerCampaignRecipient.objects.filter(
        status=CustomerCampaignRecipient.STATUS_SENT,
    ).filter(
        Q(outbound_email__isnull=True)
        | ~Q(outbound_email__status=OutboundEmail.STATUS_SENT)
    ).count()
    sent_without_unsubscribe = CustomerCampaignRecipient.objects.filter(
        status=CustomerCampaignRecipient.STATUS_SENT,
        outbound_email__status=OutboundEmail.STATUS_SENT,
    ).exclude(outbound_email__body__contains="/preferences/unsubscribe/").count()

    stale_consent_recipients = []
    active_recipients = CustomerCampaignRecipient.objects.filter(
        status__in=[
            CustomerCampaignRecipient.STATUS_PENDING,
            CustomerCampaignRecipient.STATUS_PROCESSING,
        ]
    ).select_related("campaign", "customer", "customer__marketing_preference")
    for recipient in active_recipients.iterator():
        try:
            preference = recipient.customer.marketing_preference
        except CustomerMarketingPreference.DoesNotExist:
            preference = None
        reason = ""
        if preference is None:
            reason = "preference_missing"
        elif preference.withdrawn_at is not None or not preference.email_marketing:
            reason = "email_consent_withdrawn"
        elif not getattr(preference, recipient.campaign.topic, False):
            reason = "topic_consent_withdrawn"
        elif (recipient.customer.email or "").strip().lower() != recipient.email_address.lower():
            reason = "email_changed"
        else:
            event = preference.events.order_by("-created_at", "-id").first()
            if event is None or event.action == MarketingConsentEvent.ACTION_WITHDRAWN:
                reason = "active_consent_event_missing"
            elif not event.email_marketing or not getattr(event, recipient.campaign.topic, False):
                reason = "consent_event_mismatch"
        if reason:
            stale_consent_recipients.append(
                {
                    "recipient_id": recipient.pk,
                    "campaign_id": recipient.campaign_id,
                    "reason": reason,
                }
            )

    count_mismatches = []
    limit_exceeded = []
    configured_max = int(getattr(settings, "CUSTOMER_CAMPAIGN_MAX_RECIPIENTS", 100))
    for campaign in CustomerCampaign.objects.all().iterator():
        total = campaign.recipients.count()
        sent = campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_SENT
        ).count()
        suppressed = campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_SUPPRESSED
        ).count()
        failed = campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_FAILED
        ).count()
        if (
            campaign.prepared_count != total
            or campaign.sent_count != sent
            or campaign.suppressed_count != suppressed
            or campaign.failed_count != failed
        ):
            count_mismatches.append(
                {
                    "campaign_id": campaign.pk,
                    "stored": {
                        "prepared": campaign.prepared_count,
                        "sent": campaign.sent_count,
                        "suppressed": campaign.suppressed_count,
                        "failed": campaign.failed_count,
                    },
                    "actual": {
                        "prepared": total,
                        "sent": sent,
                        "suppressed": suppressed,
                        "failed": failed,
                    },
                }
            )
        if campaign.max_recipients > configured_max or total > campaign.max_recipients:
            limit_exceeded.append(
                {
                    "campaign_id": campaign.pk,
                    "configured_max": configured_max,
                    "campaign_limit": campaign.max_recipients,
                    "prepared": total,
                }
            )

    errors = (
        approved_missing_record
        + self_approved
        + stale_processing
        + completed_with_unfinished
        + sent_without_success_log
        + sent_without_unsubscribe
        + len(stale_consent_recipients)
        + len(count_mismatches)
        + len(limit_exceeded)
    )
    return {
        "errors": errors,
        "campaign_count": CustomerCampaign.objects.count(),
        "recipient_count": CustomerCampaignRecipient.objects.count(),
        "approved_missing_record": approved_missing_record,
        "self_approved": self_approved,
        "stale_processing": stale_processing,
        "completed_with_unfinished": completed_with_unfinished,
        "sent_without_success_log": sent_without_success_log,
        "sent_without_unsubscribe": sent_without_unsubscribe,
        "stale_consent_count": len(stale_consent_recipients),
        "stale_consent_recipients": stale_consent_recipients[:50],
        "count_mismatch_count": len(count_mismatches),
        "count_mismatches": count_mismatches[:50],
        "limit_exceeded_count": len(limit_exceeded),
        "limit_exceeded": limit_exceeded[:50],
    }
