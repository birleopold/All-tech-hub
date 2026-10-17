from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils import timezone

from commerce.models import Order
from core.models import CompanySettings
from crm.models import Customer
from customer_campaigns.models import (
    CampaignAutomationEvent,
    CustomerCampaign,
    CustomerCampaignRecipient,
)
from loyalty.models import CustomerMarketingPreference, MarketingConsentEvent
from marketing.models import MarketingLead
from messaging.models import OutboundEmail
from messaging.utils import retry_outbound_email, send_queued_outbound_email


class CampaignOperationError(Exception):
    pass


def _setting_int(name: str, default: int, *, minimum: int = 1, maximum: int = 10000) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _record_automation_event(
    campaign: CustomerCampaign,
    action: str,
    *,
    actor=None,
    message: str = "",
    metadata: dict | None = None,
) -> CampaignAutomationEvent:
    return CampaignAutomationEvent.objects.create(
        campaign=campaign,
        action=action,
        actor=actor,
        message=(message or "")[:255],
        metadata=metadata or {},
    )


def _approval_deadline(campaign: CustomerCampaign):
    if campaign.approval_expires_at:
        return campaign.approval_expires_at
    if not campaign.approved_at:
        return None
    validity_hours = _setting_int(
        "CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS",
        48,
        minimum=1,
        maximum=720,
    )
    return campaign.approved_at + timedelta(hours=validity_hours)


def _approval_is_current(campaign: CustomerCampaign, *, at=None) -> bool:
    deadline = _approval_deadline(campaign)
    return bool(campaign.approved_by_id and campaign.approved_at and deadline and (at or timezone.now()) < deadline)


def eligible_customer_queryset(campaign: CustomerCampaign):
    topic_field = f"marketing_preference__{campaign.topic}"
    channel_field = (
        "marketing_preference__whatsapp_marketing"
        if campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP
        else "marketing_preference__email_marketing"
    )
    queryset = (
        Customer.objects.filter(
            **{channel_field: True},
            marketing_preference__withdrawn_at__isnull=True,
            **{topic_field: True},
        )
        .annotate(
            order_count=Count(
                "orders",
                filter=~Q(orders__status=Order.STATUS_CANCELLED),
                distinct=True,
            ),
            last_order_at=Max(
                "orders__placed_at",
                filter=~Q(orders__status=Order.STATUS_CANCELLED),
            ),
            lifetime_spend=Sum("orders__total", filter=~Q(orders__status=Order.STATUS_CANCELLED)),
        )
        .select_related("marketing_preference")
    )
    if campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP:
        queryset = queryset.exclude(phone="")
    else:
        queryset = queryset.exclude(email="")
    recent_cutoff = timezone.now() - timedelta(days=90)
    if campaign.segment == CustomerCampaign.SEGMENT_REPEAT:
        queryset = queryset.filter(order_count__gte=2)
    elif campaign.segment == CustomerCampaign.SEGMENT_RECENT:
        queryset = queryset.filter(last_order_at__gte=recent_cutoff)
    elif campaign.segment == CustomerCampaign.SEGMENT_DORMANT:
        queryset = queryset.filter(last_order_at__lt=recent_cutoff)
    elif campaign.segment == CustomerCampaign.SEGMENT_HIGH_VALUE:
        threshold = campaign.minimum_customer_spend or getattr(settings, "CUSTOMER_CAMPAIGN_HIGH_VALUE_UGX", 1000000)
        queryset = queryset.filter(lifetime_spend__gte=threshold)
    elif campaign.segment == CustomerCampaign.SEGMENT_NEW:
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))
    elif campaign.segment == CustomerCampaign.SEGMENT_NO_PURCHASE:
        queryset = queryset.filter(order_count=0)
    elif campaign.segment == CustomerCampaign.SEGMENT_PRODUCT_INTEREST:
        if not campaign.target_product_id:
            return queryset.none()
        interested_emails = MarketingLead.objects.filter(product_id=campaign.target_product_id).exclude(email="").values("email")
        queryset = queryset.filter(email__in=interested_emails)
    if campaign.minimum_customer_spend:
        queryset = queryset.filter(lifetime_spend__gte=campaign.minimum_customer_spend)
    if campaign.location_query:
        location = campaign.location_query.strip()
        queryset = queryset.filter(Q(addresses__city__icontains=location) | Q(addresses__region__icontains=location) | Q(addresses__line1__icontains=location)).distinct()
    return queryset.order_by("-last_order_at", "name", "id")


def _latest_active_event(
    preference: CustomerMarketingPreference,
    *,
    topic: str,
    channel: str = CustomerCampaign.CHANNEL_EMAIL,
) -> MarketingConsentEvent | None:
    event = preference.events.order_by("-created_at", "-id").first()
    if event is None or event.action == MarketingConsentEvent.ACTION_WITHDRAWN:
        return None
    channel_allowed = (
        event.whatsapp_marketing
        if channel == CustomerCampaign.CHANNEL_WHATSAPP
        else event.email_marketing
    )
    if not channel_allowed or not getattr(event, topic, False):
        return None
    return event


@transaction.atomic
def prepare_campaign(campaign: CustomerCampaign, *, user) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status not in {
        CustomerCampaign.STATUS_DRAFT,
        CustomerCampaign.STATUS_PREPARED,
    }:
        raise CampaignOperationError("Only draft or prepared campaigns can be prepared.")
    if campaign.recipients.filter(
        status__in=[
            CustomerCampaignRecipient.STATUS_SENT,
            CustomerCampaignRecipient.STATUS_PROCESSING,
            CustomerCampaignRecipient.STATUS_FAILED,
        ]
    ).exists():
        raise CampaignOperationError(
            "This campaign already has delivery activity and cannot be rebuilt."
        )

    configured_max = _setting_int(
        "CUSTOMER_CAMPAIGN_MAX_RECIPIENTS",
        100,
        maximum=500,
    )
    if campaign.max_recipients > configured_max:
        raise CampaignOperationError(
            f"The recipient limit exceeds the configured maximum of {configured_max}."
        )

    campaign.recipients.all().delete()
    recipients = []
    customers = list(eligible_customer_queryset(campaign)[: campaign.max_recipients])
    for customer in customers:
        preference = customer.marketing_preference
        event = _latest_active_event(
            preference, topic=campaign.topic, channel=campaign.channel
        )
        if event is None:
            continue
        recipients.append(
            CustomerCampaignRecipient(
                campaign=campaign,
                customer=customer,
                email_address=(customer.email or "").strip().lower(),
                phone_number=(customer.phone or "").strip(),
                consent_event=event,
            )
        )
    if not recipients:
        raise CampaignOperationError(
            "No customers have current matching channel and topic consent."
        )

    CustomerCampaignRecipient.objects.bulk_create(recipients)
    campaign.status = CustomerCampaign.STATUS_PREPARED
    campaign.prepared_by = user
    campaign.prepared_at = timezone.now()
    campaign.prepared_count = len(recipients)
    campaign.sent_count = 0
    campaign.suppressed_count = 0
    campaign.failed_count = 0
    campaign.approved_by = None
    campaign.approved_at = None
    campaign.approval_expires_at = None
    campaign.approval_note = ""
    campaign.failure_reason = ""
    campaign.started_at = None
    campaign.completed_at = None
    campaign.automated_delivery = False
    campaign.scheduled_for = None
    campaign.next_run_at = None
    campaign.scheduled_by = None
    campaign.scheduled_at = None
    campaign.paused_by = None
    campaign.paused_at = None
    campaign.pause_reason = ""
    campaign.last_automation_at = None
    campaign.automation_run_count = 0
    campaign.save(
        update_fields=[
            "status",
            "prepared_by",
            "prepared_at",
            "prepared_count",
            "sent_count",
            "suppressed_count",
            "failed_count",
            "approved_by",
            "approved_at",
            "approval_expires_at",
            "approval_note",
            "failure_reason",
            "started_at",
            "completed_at",
            "automated_delivery",
            "scheduled_for",
            "next_run_at",
            "scheduled_by",
            "scheduled_at",
            "paused_by",
            "paused_at",
            "pause_reason",
            "last_automation_at",
            "automation_run_count",
            "updated_at",
        ]
    )
    return campaign


@transaction.atomic
def approve_campaign(
    campaign: CustomerCampaign,
    *,
    user,
    approval_note: str = "",
) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != CustomerCampaign.STATUS_PREPARED:
        raise CampaignOperationError("Only a prepared campaign can be approved.")
    if not campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PENDING
    ).exists():
        raise CampaignOperationError("The campaign has no pending recipients.")
    if getattr(settings, "CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER", True):
        if user.pk in {campaign.created_by_id, campaign.prepared_by_id}:
            raise CampaignOperationError(
                "A different authorised staff member must approve this campaign."
            )
    approved_at = timezone.now()
    validity_hours = _setting_int(
        "CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS",
        48,
        minimum=1,
        maximum=720,
    )
    campaign.status = CustomerCampaign.STATUS_APPROVED
    campaign.approved_by = user
    campaign.approved_at = approved_at
    campaign.approval_expires_at = approved_at + timedelta(hours=validity_hours)
    campaign.approval_note = (approval_note or "").strip()
    campaign.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "approval_expires_at",
            "approval_note",
            "updated_at",
        ]
    )
    return campaign


def _current_consent(
    recipient: CustomerCampaignRecipient,
) -> tuple[CustomerMarketingPreference | None, MarketingConsentEvent | None, str]:
    customer = Customer.objects.filter(pk=recipient.customer_id).first()
    if customer is None:
        return None, None, "customer_removed"
    if recipient.campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP:
        current_phone = (customer.phone or "").strip()
        if not current_phone:
            return None, None, "phone_missing"
        if current_phone != recipient.phone_number.strip():
            return None, None, "phone_changed_reprepare_required"
    else:
        current_email = (customer.email or "").strip().lower()
        if not current_email:
            return None, None, "email_missing"
        if current_email != recipient.email_address.strip().lower():
            return None, None, "email_changed_reprepare_required"
    preference = CustomerMarketingPreference.objects.filter(
        customer_id=recipient.customer_id
    ).first()
    if preference is None:
        return None, None, "preference_missing"
    channel_allowed = (
        preference.whatsapp_marketing
        if recipient.campaign.channel == CustomerCampaign.CHANNEL_WHATSAPP
        else preference.email_marketing
    )
    if preference.withdrawn_at is not None or not channel_allowed:
        return preference, None, f"{recipient.campaign.channel}_consent_withdrawn"
    if not getattr(preference, recipient.campaign.topic, False):
        return preference, None, "topic_consent_withdrawn"
    event = _latest_active_event(
        preference,
        topic=recipient.campaign.topic,
        channel=recipient.campaign.channel,
    )
    if event is None:
        return preference, None, "active_consent_event_missing"
    return preference, event, ""


def _unsubscribe_url(preference: CustomerMarketingPreference) -> str:
    base = getattr(settings, "PUBLIC_BASE_URL", "https://leosoftug.com").rstrip("/")
    path = reverse(
        "marketing_unsubscribe_all",
        kwargs={"token": preference.unsubscribe_token},
    )
    return f"{base}{path}"


def _render_template(
    template: str,
    *,
    customer: Customer,
    company_name: str,
    unsubscribe_url: str,
) -> str:
    first_name = (customer.name or "Customer").strip().split(" ", 1)[0]
    values = {
        "customer_name": customer.name or "Customer",
        "first_name": first_name,
        "company": company_name,
        "unsubscribe_url": unsubscribe_url,
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


@transaction.atomic
def _claim_recipient(recipient_id: int) -> CustomerCampaignRecipient | None:
    recipient = (
        CustomerCampaignRecipient.objects.select_for_update()
        .select_related("campaign", "customer")
        .filter(pk=recipient_id)
        .first()
    )
    if recipient is None or recipient.status != CustomerCampaignRecipient.STATUS_PENDING:
        return None
    preference, event, reason = _current_consent(recipient)
    if reason or preference is None or event is None:
        recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
        recipient.suppression_reason = reason or "consent_recheck_failed"
        recipient.attempted_at = timezone.now()
        recipient.save(
            update_fields=[
                "status",
                "suppression_reason",
                "attempted_at",
                "updated_at",
            ]
        )
        return None
    recipient.status = CustomerCampaignRecipient.STATUS_PROCESSING
    recipient.consent_event = event
    recipient.suppression_reason = ""
    recipient.attempted_at = timezone.now()
    recipient.save(
        update_fields=[
            "status",
            "consent_event",
            "suppression_reason",
            "attempted_at",
            "updated_at",
        ]
    )
    return recipient


@transaction.atomic
def _suppress_processing(recipient_id: int, reason: str) -> None:
    recipient = CustomerCampaignRecipient.objects.select_for_update().filter(
        pk=recipient_id,
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
    ).first()
    if recipient is None:
        return
    recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
    recipient.suppression_reason = reason
    recipient.save(update_fields=["status", "suppression_reason", "updated_at"])


@transaction.atomic
def _create_delivery_log(
    recipient_id: int,
    *,
    subject: str,
    body: str,
    user,
) -> OutboundEmail | None:
    recipient = CustomerCampaignRecipient.objects.select_for_update().filter(
        pk=recipient_id,
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
        outbound_email__isnull=True,
    ).first()
    if recipient is None:
        return None
    log = OutboundEmail.objects.create(
        to_email=recipient.email_address,
        subject=(subject or "")[:200],
        body=body,
        status=OutboundEmail.STATUS_QUEUED,
        category=OutboundEmail.CATEGORY_MARKETING,
        created_by=user,
    )
    recipient.outbound_email = log
    recipient.save(update_fields=["outbound_email", "updated_at"])
    return log


@transaction.atomic
def _finalize_delivery(
    recipient_id: int,
    *,
    log: OutboundEmail,
    event: MarketingConsentEvent,
) -> None:
    recipient = CustomerCampaignRecipient.objects.select_for_update().filter(
        pk=recipient_id,
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
        outbound_email_id=log.pk,
    ).first()
    if recipient is None:
        return
    recipient.consent_event = event
    if log.status == OutboundEmail.STATUS_SENT:
        recipient.status = CustomerCampaignRecipient.STATUS_SENT
        recipient.sent_at = log.sent_at or timezone.now()
        recipient.suppression_reason = ""
    else:
        recipient.status = CustomerCampaignRecipient.STATUS_FAILED
        recipient.suppression_reason = (log.error or "email_delivery_failed")[:160]
    recipient.save(
        update_fields=[
            "consent_event",
            "status",
            "sent_at",
            "suppression_reason",
            "updated_at",
        ]
    )


def _reconcile_linked_processing(campaign: CustomerCampaign) -> None:
    recipients = campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
        outbound_email__isnull=False,
    ).select_related("outbound_email", "consent_event")
    for recipient in recipients.iterator():
        log = recipient.outbound_email
        if log.status not in {OutboundEmail.STATUS_SENT, OutboundEmail.STATUS_FAILED}:
            continue
        event = recipient.consent_event
        if event is None:
            continue
        _finalize_delivery(recipient.pk, log=log, event=event)


def refresh_campaign_counts(campaign: CustomerCampaign) -> CustomerCampaign:
    counts = {
        status: campaign.recipients.filter(status=status).count()
        for status in dict(CustomerCampaignRecipient.STATUS_CHOICES)
    }
    campaign.prepared_count = campaign.recipients.count()
    campaign.sent_count = counts.get(CustomerCampaignRecipient.STATUS_SENT, 0)
    campaign.suppressed_count = counts.get(
        CustomerCampaignRecipient.STATUS_SUPPRESSED, 0
    )
    campaign.failed_count = counts.get(CustomerCampaignRecipient.STATUS_FAILED, 0)
    unfinished = counts.get(CustomerCampaignRecipient.STATUS_PENDING, 0) + counts.get(
        CustomerCampaignRecipient.STATUS_PROCESSING, 0
    )
    if campaign.status not in {
        CustomerCampaign.STATUS_CANCELLED,
        CustomerCampaign.STATUS_EXPIRED,
        CustomerCampaign.STATUS_FAILED,
    }:
        if unfinished == 0 and campaign.prepared_count:
            campaign.status = CustomerCampaign.STATUS_COMPLETED
            campaign.completed_at = campaign.completed_at or timezone.now()
            campaign.automated_delivery = False
            campaign.next_run_at = None
        elif campaign.status in {
            CustomerCampaign.STATUS_APPROVED,
            CustomerCampaign.STATUS_SENDING,
        }:
            campaign.status = CustomerCampaign.STATUS_SENDING
    campaign.save(
        update_fields=[
            "prepared_count",
            "sent_count",
            "suppressed_count",
            "failed_count",
            "status",
            "completed_at",
            "automated_delivery",
            "next_run_at",
            "updated_at",
        ]
    )
    return campaign


@transaction.atomic
def _expire_locked_campaign(
    campaign: CustomerCampaign,
    *,
    message: str = "Campaign approval expired before remaining delivery.",
) -> CustomerCampaign:
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        campaign.status = CustomerCampaign.STATUS_PAUSED
        campaign.pause_reason = "approval_expired_with_processing_delivery"
        campaign.paused_at = timezone.now()
        campaign.next_run_at = None
        campaign.save(
            update_fields=[
                "status",
                "pause_reason",
                "paused_at",
                "next_run_at",
                "updated_at",
            ]
        )
        _record_automation_event(
            campaign,
            CampaignAutomationEvent.ACTION_PAUSED,
            message="Approval expired while a delivery was processing; manual review required.",
        )
        return campaign

    campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PENDING
    ).update(
        status=CustomerCampaignRecipient.STATUS_SUPPRESSED,
        suppression_reason="campaign_approval_expired",
        attempted_at=timezone.now(),
    )
    campaign.status = CustomerCampaign.STATUS_EXPIRED
    campaign.automated_delivery = False
    campaign.next_run_at = None
    campaign.failure_reason = message
    campaign.completed_at = timezone.now()
    campaign.save(
        update_fields=[
            "status",
            "automated_delivery",
            "next_run_at",
            "failure_reason",
            "completed_at",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_EXPIRED,
        message=message,
    )
    return refresh_campaign_counts(campaign)


def expire_campaign_if_needed(campaign: CustomerCampaign) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.get(pk=campaign.pk)
    deadline = _approval_deadline(campaign)
    if deadline and timezone.now() >= deadline and campaign.status in {
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SCHEDULED,
        CustomerCampaign.STATUS_SENDING,
        CustomerCampaign.STATUS_PAUSED,
    }:
        with transaction.atomic():
            locked = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
            return _expire_locked_campaign(locked)
    return campaign


def send_campaign_batch(
    campaign: CustomerCampaign,
    *,
    user,
    batch_size: int | None = None,
    automated: bool = False,
) -> CustomerCampaign:
    if campaign.channel != CustomerCampaign.CHANNEL_EMAIL:
        raise CampaignOperationError(
            "WhatsApp campaigns use the consent-safe manual click-to-chat queue."
        )
    if not getattr(settings, "CUSTOMER_CAMPAIGN_SEND_ENABLED", False):
        raise CampaignOperationError(
            "Customer campaign sending is disabled by the production safety switch."
        )
    campaign.refresh_from_db()
    if automated:
        if not campaign.automated_delivery or campaign.status != CustomerCampaign.STATUS_SENDING:
            raise CampaignOperationError("The scheduled campaign is not claimed for automation.")
    else:
        if campaign.automated_delivery:
            raise CampaignOperationError(
                "This campaign is in scheduled-delivery mode. Pause or cancel the schedule instead."
            )
        if campaign.status not in {
            CustomerCampaign.STATUS_APPROVED,
            CustomerCampaign.STATUS_SENDING,
        }:
            raise CampaignOperationError("The campaign must be approved before sending.")
        if user is None:
            raise CampaignOperationError("A staff user is required for manual delivery.")
    if not campaign.approved_by_id or not campaign.approved_at:
        raise CampaignOperationError("The campaign approval record is incomplete.")
    if not _approval_is_current(campaign):
        expire_campaign_if_needed(campaign)
        raise CampaignOperationError("The campaign approval has expired.")

    _reconcile_linked_processing(campaign)
    configured_batch = (
        _setting_int("CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE", 1, maximum=50)
        if automated
        else _setting_int("CUSTOMER_CAMPAIGN_BATCH_SIZE", 10, maximum=50)
    )
    requested_batch = int(batch_size or configured_batch)
    batch_limit = max(1, min(requested_batch, configured_batch))
    stale_cutoff = timezone.now() - timedelta(minutes=30)
    campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING,
        attempted_at__lt=stale_cutoff,
        outbound_email__isnull=True,
    ).update(
        status=CustomerCampaignRecipient.STATUS_PENDING,
        suppression_reason="",
    )

    if campaign.status == CustomerCampaign.STATUS_APPROVED:
        campaign.status = CustomerCampaign.STATUS_SENDING
        campaign.started_at = timezone.now()
        campaign.sent_by = user
        campaign.save(
            update_fields=["status", "started_at", "sent_by", "updated_at"]
        )

    recipient_ids = list(
        campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_PENDING
        ).order_by("id").values_list("id", flat=True)[:batch_limit]
    )
    company_name = CompanySettings.load().company_name
    for recipient_id in recipient_ids:
        recipient = _claim_recipient(recipient_id)
        if recipient is None:
            continue
        recipient = CustomerCampaignRecipient.objects.select_related(
            "campaign", "customer"
        ).get(pk=recipient_id)
        preference, event, reason = _current_consent(recipient)
        if reason or preference is None or event is None:
            _suppress_processing(recipient_id, reason or "consent_recheck_failed")
            continue

        unsubscribe_url = _unsubscribe_url(preference)
        subject = _render_template(
            campaign.subject,
            customer=recipient.customer,
            company_name=company_name,
            unsubscribe_url=unsubscribe_url,
        )
        body = _render_template(
            campaign.body,
            customer=recipient.customer,
            company_name=company_name,
            unsubscribe_url=unsubscribe_url,
        )
        if "{unsubscribe_url}" not in campaign.body:
            body = (
                f"{body.rstrip()}\n\nManage optional marketing preferences: "
                f"{unsubscribe_url}"
            )
        log = _create_delivery_log(
            recipient_id,
            subject=subject,
            body=body,
            user=user,
        )
        if log is None:
            continue
        # A freshly queued message needs a first send, not a retry.
        # Retried/uncertain deliveries must not be automatically replayed.
        send_queued_outbound_email(log)
        log.refresh_from_db()
        _finalize_delivery(recipient_id, log=log, event=event)

    return refresh_campaign_counts(campaign)


def _whatsapp_digits(raw_phone: str) -> str:
    digits = "".join(character for character in (raw_phone or "") if character.isdigit())
    if digits.startswith("0") and len(digits) >= 10:
        digits = "256" + digits[1:]
    return digits


@transaction.atomic
def open_whatsapp_recipient(recipient: CustomerCampaignRecipient, *, user) -> str | None:
    recipient = (
        CustomerCampaignRecipient.objects.select_for_update()
        .select_related("campaign", "customer")
        .get(pk=recipient.pk)
    )
    campaign = recipient.campaign
    if campaign.channel != CustomerCampaign.CHANNEL_WHATSAPP:
        raise CampaignOperationError("This recipient does not belong to a WhatsApp campaign.")
    if campaign.status not in {
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SENDING,
    }:
        raise CampaignOperationError("Approve the WhatsApp campaign before opening messages.")
    if recipient.status != CustomerCampaignRecipient.STATUS_PENDING:
        raise CampaignOperationError("Only pending recipients can be opened for WhatsApp.")
    if not _approval_is_current(campaign):
        raise CampaignOperationError("The campaign approval has expired.")
    preference, event, reason = _current_consent(recipient)
    if reason or preference is None or event is None:
        recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
        recipient.suppression_reason = reason or "consent_recheck_failed"
        recipient.attempted_at = timezone.now()
        recipient.save(
            update_fields=["status", "suppression_reason", "attempted_at", "updated_at"]
        )
        refresh_campaign_counts(campaign)
        return None
    digits = _whatsapp_digits(recipient.phone_number)
    if len(digits) < 10:
        raise CampaignOperationError("The saved phone number is not valid for WhatsApp.")
    company_name = CompanySettings.load().company_name
    unsubscribe_url = _unsubscribe_url(preference)
    message = _render_template(
        campaign.body,
        customer=recipient.customer,
        company_name=company_name,
        unsubscribe_url=unsubscribe_url,
    )
    if "{unsubscribe_url}" not in campaign.body:
        message = (
            f"{message.rstrip()}\n\nManage optional marketing preferences: "
            f"{unsubscribe_url}"
        )
    recipient.attempted_at = timezone.now()
    recipient.consent_event = event
    recipient.suppression_reason = ""
    recipient.save(
        update_fields=[
            "attempted_at",
            "consent_event",
            "suppression_reason",
            "updated_at",
        ]
    )
    if campaign.status == CustomerCampaign.STATUS_APPROVED:
        campaign.status = CustomerCampaign.STATUS_SENDING
        campaign.started_at = timezone.now()
        campaign.sent_by = user
        campaign.save(
            update_fields=["status", "started_at", "sent_by", "updated_at"]
        )
    return f"https://wa.me/{digits}?text={quote(message)}"


@transaction.atomic
def mark_whatsapp_recipient_sent(
    recipient: CustomerCampaignRecipient, *, user
) -> CustomerCampaign:
    recipient = (
        CustomerCampaignRecipient.objects.select_for_update()
        .select_related("campaign", "customer")
        .get(pk=recipient.pk)
    )
    campaign = recipient.campaign
    if campaign.channel != CustomerCampaign.CHANNEL_WHATSAPP:
        raise CampaignOperationError("This recipient does not belong to a WhatsApp campaign.")
    if recipient.status != CustomerCampaignRecipient.STATUS_PENDING:
        raise CampaignOperationError("Only pending recipients can be confirmed as sent.")
    if not _approval_is_current(campaign):
        raise CampaignOperationError("The campaign approval expired before confirmation.")
    if not recipient.attempted_at:
        raise CampaignOperationError("Open the WhatsApp message before confirming it as sent.")
    preference, event, reason = _current_consent(recipient)
    if reason or preference is None or event is None:
        recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
        recipient.suppression_reason = reason or "consent_recheck_failed"
        recipient.save(update_fields=["status", "suppression_reason", "updated_at"])
        return refresh_campaign_counts(campaign)
    recipient.status = CustomerCampaignRecipient.STATUS_SENT
    recipient.sent_at = timezone.now()
    recipient.consent_event = event
    recipient.suppression_reason = ""
    recipient.save(
        update_fields=[
            "status",
            "sent_at",
            "consent_event",
            "suppression_reason",
            "updated_at",
        ]
    )
    if campaign.sent_by_id is None:
        campaign.sent_by = user
        campaign.save(update_fields=["sent_by", "updated_at"])
    return refresh_campaign_counts(campaign)


@transaction.atomic
def schedule_campaign(
    campaign: CustomerCampaign,
    *,
    user,
    scheduled_for,
    batch_size: int,
) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.channel != CustomerCampaign.CHANNEL_EMAIL:
        raise CampaignOperationError(
            "WhatsApp campaigns are intentionally manual and cannot be scheduled."
        )
    if campaign.status != CustomerCampaign.STATUS_APPROVED:
        raise CampaignOperationError("Only an approved campaign can be scheduled.")
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        raise CampaignOperationError("A processing recipient prevents scheduling.")
    if not _approval_is_current(campaign):
        return _expire_locked_campaign(campaign)

    now = timezone.now()
    if scheduled_for <= now:
        raise CampaignOperationError("Choose a future schedule time.")
    deadline = _approval_deadline(campaign)
    if deadline is None or scheduled_for >= deadline:
        raise CampaignOperationError(
            "The scheduled time must be before the approval expiry time."
        )
    max_lead_hours = _setting_int(
        "CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS",
        24,
        minimum=1,
        maximum=720,
    )
    if scheduled_for > now + timedelta(hours=max_lead_hours):
        raise CampaignOperationError(
            f"Schedule this campaign within the next {max_lead_hours} hours."
        )
    configured_batch = _setting_int(
        "CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE",
        1,
        maximum=50,
    )
    safe_batch = max(1, min(int(batch_size or configured_batch), configured_batch))

    campaign.status = CustomerCampaign.STATUS_SCHEDULED
    campaign.automated_delivery = True
    campaign.scheduled_for = scheduled_for
    campaign.next_run_at = scheduled_for
    campaign.automation_batch_size = safe_batch
    campaign.scheduled_by = user
    campaign.scheduled_at = now
    campaign.paused_by = None
    campaign.paused_at = None
    campaign.pause_reason = ""
    campaign.failure_reason = ""
    campaign.save(
        update_fields=[
            "status",
            "automated_delivery",
            "scheduled_for",
            "next_run_at",
            "automation_batch_size",
            "scheduled_by",
            "scheduled_at",
            "paused_by",
            "paused_at",
            "pause_reason",
            "failure_reason",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_SCHEDULED,
        actor=user,
        message="Campaign scheduled for automated bounded delivery.",
        metadata={
            "scheduled_for": scheduled_for.isoformat(),
            "batch_size": safe_batch,
            "approval_expires_at": deadline.isoformat(),
        },
    )
    return campaign


@transaction.atomic
def pause_campaign(
    campaign: CustomerCampaign,
    *,
    user,
    reason: str,
    automatic: bool = False,
) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if not campaign.automated_delivery or campaign.status not in {
        CustomerCampaign.STATUS_SCHEDULED,
        CustomerCampaign.STATUS_SENDING,
    }:
        raise CampaignOperationError("Only an active scheduled campaign can be paused.")
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        raise CampaignOperationError(
            "A recipient is processing. Disable scheduler and send switches, then review delivery evidence."
        )
    campaign.status = CustomerCampaign.STATUS_PAUSED
    campaign.next_run_at = None
    campaign.paused_by = user
    campaign.paused_at = timezone.now()
    campaign.pause_reason = (reason or "Campaign paused.")[:240]
    campaign.save(
        update_fields=[
            "status",
            "next_run_at",
            "paused_by",
            "paused_at",
            "pause_reason",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_PAUSED,
        actor=user,
        message=campaign.pause_reason,
        metadata={"automatic": bool(automatic)},
    )
    return campaign


@transaction.atomic
def resume_campaign(
    campaign: CustomerCampaign,
    *,
    user,
    next_run_at,
) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != CustomerCampaign.STATUS_PAUSED or not campaign.automated_delivery:
        raise CampaignOperationError("Only a paused scheduled campaign can be resumed.")
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        raise CampaignOperationError("Processing delivery evidence must be resolved first.")
    if not _approval_is_current(campaign):
        return _expire_locked_campaign(campaign)
    now = timezone.now()
    if next_run_at < now:
        next_run_at = now
    deadline = _approval_deadline(campaign)
    if deadline is None or next_run_at >= deadline:
        raise CampaignOperationError("Resume time must be before approval expiry.")
    campaign.status = CustomerCampaign.STATUS_SCHEDULED
    campaign.next_run_at = next_run_at
    campaign.paused_by = None
    campaign.paused_at = None
    campaign.pause_reason = ""
    campaign.save(
        update_fields=[
            "status",
            "next_run_at",
            "paused_by",
            "paused_at",
            "pause_reason",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_RESUMED,
        actor=user,
        message="Scheduled delivery resumed.",
        metadata={"next_run_at": next_run_at.isoformat()},
    )
    return campaign


@transaction.atomic
def _claim_due_campaign(campaign_id: int) -> CustomerCampaign | None:
    campaign = CustomerCampaign.objects.select_for_update().filter(pk=campaign_id).first()
    now = timezone.now()
    if (
        campaign is None
        or campaign.status != CustomerCampaign.STATUS_SCHEDULED
        or not campaign.automated_delivery
        or not campaign.next_run_at
        or campaign.next_run_at > now
    ):
        return None
    if not _approval_is_current(campaign, at=now):
        _expire_locked_campaign(campaign)
        return None
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        campaign.status = CustomerCampaign.STATUS_PAUSED
        campaign.next_run_at = None
        campaign.paused_at = now
        campaign.pause_reason = "processing_delivery_requires_manual_review"
        campaign.save(
            update_fields=[
                "status",
                "next_run_at",
                "paused_at",
                "pause_reason",
                "updated_at",
            ]
        )
        _record_automation_event(
            campaign,
            CampaignAutomationEvent.ACTION_PAUSED,
            message=campaign.pause_reason,
            metadata={"automatic": True},
        )
        return None
    campaign.status = CustomerCampaign.STATUS_SENDING
    campaign.next_run_at = None
    campaign.last_automation_at = now
    campaign.automation_run_count += 1
    campaign.started_at = campaign.started_at or now
    campaign.save(
        update_fields=[
            "status",
            "next_run_at",
            "last_automation_at",
            "automation_run_count",
            "started_at",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_BATCH_STARTED,
        message="Automated campaign batch claimed.",
        metadata={"run": campaign.automation_run_count},
    )
    return campaign


def _failure_circuit_open(campaign: CustomerCampaign) -> bool:
    attempts = campaign.sent_count + campaign.failed_count
    minimum = _setting_int(
        "CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS",
        3,
        minimum=1,
        maximum=1000,
    )
    threshold = _setting_int(
        "CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT",
        50,
        minimum=1,
        maximum=100,
    )
    return attempts >= minimum and campaign.failed_count * 100 >= attempts * threshold


def _finish_automated_batch(
    campaign: CustomerCampaign,
    *,
    before: dict,
) -> tuple[CustomerCampaign, str]:
    campaign.refresh_from_db()
    campaign = refresh_campaign_counts(campaign)
    deltas = {
        "sent": campaign.sent_count - before["sent"],
        "suppressed": campaign.suppressed_count - before["suppressed"],
        "failed": campaign.failed_count - before["failed"],
    }
    if campaign.status == CustomerCampaign.STATUS_COMPLETED:
        _record_automation_event(
            campaign,
            CampaignAutomationEvent.ACTION_COMPLETED,
            message="Scheduled campaign completed.",
            metadata=deltas,
        )
        return campaign, "completed"

    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        campaign.status = CustomerCampaign.STATUS_PAUSED
        campaign.next_run_at = None
        campaign.paused_at = timezone.now()
        campaign.pause_reason = "uncertain_processing_delivery_requires_review"
        campaign.save(
            update_fields=[
                "status",
                "next_run_at",
                "paused_at",
                "pause_reason",
                "updated_at",
            ]
        )
        _record_automation_event(
            campaign,
            CampaignAutomationEvent.ACTION_PAUSED,
            message=campaign.pause_reason,
            metadata={"automatic": True, **deltas},
        )
        return campaign, "paused"

    if _failure_circuit_open(campaign) and campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PENDING
    ).exists():
        campaign.status = CustomerCampaign.STATUS_PAUSED
        campaign.next_run_at = None
        campaign.paused_at = timezone.now()
        campaign.pause_reason = "delivery_failure_rate_circuit_breaker"
        campaign.save(
            update_fields=[
                "status",
                "next_run_at",
                "paused_at",
                "pause_reason",
                "updated_at",
            ]
        )
        _record_automation_event(
            campaign,
            CampaignAutomationEvent.ACTION_PAUSED,
            message=campaign.pause_reason,
            metadata={"automatic": True, **deltas},
        )
        return campaign, "paused"

    interval_minutes = _setting_int(
        "CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES",
        15,
        minimum=5,
        maximum=1440,
    )
    next_run = timezone.now() + timedelta(minutes=interval_minutes)
    deadline = _approval_deadline(campaign)
    if deadline is None or next_run >= deadline:
        with transaction.atomic():
            locked = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
            return _expire_locked_campaign(locked), "expired"
    campaign.status = CustomerCampaign.STATUS_SCHEDULED
    campaign.next_run_at = next_run
    campaign.save(update_fields=["status", "next_run_at", "updated_at"])
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_BATCH_FINISHED,
        message="Automated batch finished; next bounded batch scheduled.",
        metadata={"next_run_at": next_run.isoformat(), **deltas},
    )
    return campaign, "scheduled"


def process_scheduled_campaigns(*, limit: int = 10, dry_run: bool = False) -> dict:
    now = timezone.now()
    limit = max(1, min(int(limit or 10), 100))
    active_statuses = [
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SCHEDULED,
        CustomerCampaign.STATUS_SENDING,
        CustomerCampaign.STATUS_PAUSED,
    ]
    expired_ids = list(
        CustomerCampaign.objects.filter(
            status__in=active_statuses,
            approval_expires_at__isnull=False,
            approval_expires_at__lte=now,
        ).order_by("approval_expires_at", "id").values_list("id", flat=True)[:limit]
    )
    due_ids = list(
        CustomerCampaign.objects.filter(
            status=CustomerCampaign.STATUS_SCHEDULED,
            automated_delivery=True,
            next_run_at__isnull=False,
            next_run_at__lte=now,
        ).order_by("next_run_at", "id").values_list("id", flat=True)[:limit]
    )
    summary = {
        "due": len(due_ids),
        "expired": len(expired_ids),
        "processed": 0,
        "sent": 0,
        "suppressed": 0,
        "failed": 0,
        "paused": 0,
        "completed": 0,
        "disabled": False,
    }
    if dry_run:
        return summary

    for campaign_id in expired_ids:
        with transaction.atomic():
            campaign = CustomerCampaign.objects.select_for_update().filter(pk=campaign_id).first()
            if campaign and campaign.status in active_statuses and not _approval_is_current(campaign):
                _expire_locked_campaign(campaign)

    if not getattr(settings, "CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED", False) or not getattr(
        settings,
        "CUSTOMER_CAMPAIGN_SEND_ENABLED",
        False,
    ):
        summary["disabled"] = True
        return summary

    for campaign_id in due_ids:
        campaign = _claim_due_campaign(campaign_id)
        if campaign is None:
            continue
        before = {
            "sent": campaign.sent_count,
            "suppressed": campaign.suppressed_count,
            "failed": campaign.failed_count,
        }
        try:
            campaign = send_campaign_batch(
                campaign,
                user=None,
                batch_size=campaign.automation_batch_size,
                automated=True,
            )
        except CampaignOperationError as exc:
            campaign.refresh_from_db()
            if campaign.status == CustomerCampaign.STATUS_SENDING:
                campaign.status = CustomerCampaign.STATUS_PAUSED
                campaign.next_run_at = None
                campaign.paused_at = timezone.now()
                campaign.pause_reason = f"automation_error: {str(exc)[:210]}"
                campaign.save(
                    update_fields=[
                        "status",
                        "next_run_at",
                        "paused_at",
                        "pause_reason",
                        "updated_at",
                    ]
                )
                _record_automation_event(
                    campaign,
                    CampaignAutomationEvent.ACTION_FAILED,
                    message=campaign.pause_reason,
                )
                summary["paused"] += 1
            continue
        campaign, outcome = _finish_automated_batch(campaign, before=before)
        summary["processed"] += 1
        summary["sent"] += max(0, campaign.sent_count - before["sent"])
        summary["suppressed"] += max(
            0,
            campaign.suppressed_count - before["suppressed"],
        )
        summary["failed"] += max(0, campaign.failed_count - before["failed"])
        if outcome == "paused":
            summary["paused"] += 1
        elif outcome == "completed":
            summary["completed"] += 1
        elif outcome == "expired":
            summary["expired"] += 1
    return summary


@transaction.atomic
def cancel_campaign(campaign: CustomerCampaign, *, user) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status in {
        CustomerCampaign.STATUS_COMPLETED,
        CustomerCampaign.STATUS_CANCELLED,
        CustomerCampaign.STATUS_EXPIRED,
    }:
        raise CampaignOperationError("This campaign can no longer be cancelled.")
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        raise CampaignOperationError(
            "A recipient is currently processing. Disable scheduler and send switches, "
            "then review delivery evidence before cancelling."
        )
    campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PENDING
    ).update(
        status=CustomerCampaignRecipient.STATUS_SUPPRESSED,
        suppression_reason="campaign_cancelled",
        attempted_at=timezone.now(),
    )
    campaign.status = CustomerCampaign.STATUS_CANCELLED
    campaign.automated_delivery = False
    campaign.next_run_at = None
    campaign.failure_reason = f"Cancelled by {getattr(user, 'get_username', lambda: 'staff')()}"
    campaign.completed_at = timezone.now()
    campaign.save(
        update_fields=[
            "status",
            "automated_delivery",
            "next_run_at",
            "failure_reason",
            "completed_at",
            "updated_at",
        ]
    )
    _record_automation_event(
        campaign,
        CampaignAutomationEvent.ACTION_CANCELLED,
        actor=user,
        message=campaign.failure_reason,
    )
    return refresh_campaign_counts(campaign)
