from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from customer_campaigns.models import (
    CampaignAutomationEvent,
    CustomerCampaign,
    CustomerCampaignRecipient,
)
from loyalty.models import CustomerMarketingPreference, MarketingConsentEvent
from messaging.models import OutboundEmail


def campaign_integrity_findings() -> dict:
    now = timezone.now()
    stale_cutoff = now - timedelta(minutes=30)
    grace_minutes = max(
        15,
        int(getattr(settings, "CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES", 15)) * 2,
    )
    overdue_cutoff = now - timedelta(minutes=grace_minutes)
    active_approved_statuses = [
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SCHEDULED,
        CustomerCampaign.STATUS_SENDING,
        CustomerCampaign.STATUS_PAUSED,
    ]
    approval_evidence_statuses = [
        *active_approved_statuses,
        CustomerCampaign.STATUS_COMPLETED,
        CustomerCampaign.STATUS_EXPIRED,
    ]

    approved_missing_record = CustomerCampaign.objects.filter(
        status__in=approval_evidence_statuses
    ).filter(Q(approved_by__isnull=True) | Q(approved_at__isnull=True)).count()
    active_missing_expiry = CustomerCampaign.objects.filter(
        status__in=active_approved_statuses,
        approval_expires_at__isnull=True,
    ).count()
    active_expired_approval = CustomerCampaign.objects.filter(
        status__in=active_approved_statuses,
        approval_expires_at__isnull=False,
        approval_expires_at__lte=now,
    ).count()

    self_approved = 0
    if getattr(settings, "CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER", True):
        self_approved = CustomerCampaign.objects.filter(
            status__in=approval_evidence_statuses,
            approved_by__isnull=False,
        ).filter(
            Q(approved_by_id=F("created_by_id"))
            | Q(approved_by_id=F("prepared_by_id"))
        ).count()

    scheduled_missing_control = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_SCHEDULED
    ).filter(
        Q(automated_delivery=False)
        | Q(next_run_at__isnull=True)
        | Q(scheduled_for__isnull=True)
        | Q(scheduled_at__isnull=True)
        | Q(scheduled_by__isnull=True)
    ).count()
    scheduled_without_event = CustomerCampaign.objects.filter(
        scheduled_for__isnull=False,
    ).exclude(
        automation_events__action=CampaignAutomationEvent.ACTION_SCHEDULED
    ).count()
    paused_missing_reason = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_PAUSED
    ).filter(Q(pause_reason="") | Q(paused_at__isnull=True)).count()
    paused_without_event = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_PAUSED
    ).exclude(
        automation_events__action=CampaignAutomationEvent.ACTION_PAUSED
    ).count()
    expired_with_pending = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_EXPIRED,
        recipients__status=CustomerCampaignRecipient.STATUS_PENDING,
    ).distinct().count()
    completed_schedule_without_event = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_COMPLETED,
        scheduled_for__isnull=False,
    ).exclude(
        automation_events__action=CampaignAutomationEvent.ACTION_COMPLETED
    ).count()
    overdue_schedules = CustomerCampaign.objects.filter(
        status=CustomerCampaign.STATUS_SCHEDULED,
        automated_delivery=True,
        next_run_at__lt=overdue_cutoff,
    ).count()

    configured_automation_batch = int(
        getattr(settings, "CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE", 1)
    )
    unsafe_automation_batch = CustomerCampaign.objects.filter(
        automated_delivery=True,
        automation_batch_size__gt=configured_automation_batch,
    ).count()
    invalid_automation_state = CustomerCampaign.objects.filter(
        automated_delivery=True,
    ).exclude(
        status__in=[
            CustomerCampaign.STATUS_SCHEDULED,
            CustomerCampaign.STATUS_SENDING,
            CustomerCampaign.STATUS_PAUSED,
        ]
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
        campaign__channel=CustomerCampaign.CHANNEL_EMAIL,
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
        elif preference.withdrawn_at is not None:
            reason = "marketing_consent_withdrawn"
        elif (
            recipient.campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP
            and not preference.whatsapp_marketing
        ):
            reason = "whatsapp_consent_withdrawn"
        elif (
            recipient.campaign.channel == CustomerCampaign.CHANNEL_EMAIL
            and not preference.email_marketing
        ):
            reason = "email_consent_withdrawn"
        elif not getattr(preference, recipient.campaign.topic, False):
            reason = "topic_consent_withdrawn"
        elif (
            recipient.campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP
            and (recipient.customer.phone or "").strip() != recipient.phone_number.strip()
        ):
            reason = "phone_changed"
        elif (
            recipient.campaign.channel == CustomerCampaign.CHANNEL_EMAIL
            and (recipient.customer.email or "").strip().lower()
            != recipient.email_address.lower()
        ):
            reason = "email_changed"
        else:
            event = preference.events.order_by("-created_at", "-id").first()
            if event is None or event.action == MarketingConsentEvent.ACTION_WITHDRAWN:
                reason = "active_consent_event_missing"
            elif (
                recipient.campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP
                and not event.whatsapp_marketing
            ) or (
                recipient.campaign.channel == CustomerCampaign.CHANNEL_EMAIL
                and not event.email_marketing
            ) or not getattr(event, recipient.campaign.topic, False):
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
    run_count_mismatches = []
    configured_max = int(getattr(settings, "CUSTOMER_CAMPAIGN_MAX_RECIPIENTS", 100))
    campaigns = CustomerCampaign.objects.annotate(
        started_event_count=Count(
            "automation_events",
            filter=Q(
                automation_events__action=CampaignAutomationEvent.ACTION_BATCH_STARTED
            ),
        )
    )
    for campaign in campaigns.iterator():
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
        if campaign.automation_run_count != campaign.started_event_count:
            run_count_mismatches.append(
                {
                    "campaign_id": campaign.pk,
                    "stored_runs": campaign.automation_run_count,
                    "started_events": campaign.started_event_count,
                }
            )

    errors = (
        approved_missing_record
        + active_missing_expiry
        + active_expired_approval
        + self_approved
        + scheduled_missing_control
        + scheduled_without_event
        + paused_missing_reason
        + paused_without_event
        + expired_with_pending
        + completed_schedule_without_event
        + unsafe_automation_batch
        + invalid_automation_state
        + stale_processing
        + completed_with_unfinished
        + sent_without_success_log
        + sent_without_unsubscribe
        + len(stale_consent_recipients)
        + len(count_mismatches)
        + len(limit_exceeded)
        + len(run_count_mismatches)
    )
    return {
        "errors": errors,
        "warnings": overdue_schedules,
        "campaign_count": CustomerCampaign.objects.count(),
        "recipient_count": CustomerCampaignRecipient.objects.count(),
        "automation_event_count": CampaignAutomationEvent.objects.count(),
        "approved_missing_record": approved_missing_record,
        "active_missing_expiry": active_missing_expiry,
        "active_expired_approval": active_expired_approval,
        "self_approved": self_approved,
        "scheduled_missing_control": scheduled_missing_control,
        "scheduled_without_event": scheduled_without_event,
        "paused_missing_reason": paused_missing_reason,
        "paused_without_event": paused_without_event,
        "expired_with_pending": expired_with_pending,
        "completed_schedule_without_event": completed_schedule_without_event,
        "overdue_schedules": overdue_schedules,
        "unsafe_automation_batch": unsafe_automation_batch,
        "invalid_automation_state": invalid_automation_state,
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
        "run_count_mismatch_count": len(run_count_mismatches),
        "run_count_mismatches": run_count_mismatches[:50],
    }
