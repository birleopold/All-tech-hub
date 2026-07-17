from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone

from commerce.models import Order
from core.models import CompanySettings
from crm.models import Customer
from customer_campaigns.models import CustomerCampaign, CustomerCampaignRecipient
from loyalty.models import CustomerMarketingPreference, MarketingConsentEvent
from messaging.models import OutboundEmail
from messaging.utils import retry_outbound_email


class CampaignOperationError(Exception):
    pass


def eligible_customer_queryset(campaign: CustomerCampaign):
    if campaign.channel != CustomerCampaign.CHANNEL_EMAIL:
        return Customer.objects.none()

    topic_field = f"marketing_preference__{campaign.topic}"
    queryset = (
        Customer.objects.filter(
            marketing_preference__email_marketing=True,
            marketing_preference__withdrawn_at__isnull=True,
            **{topic_field: True},
        )
        .exclude(email="")
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
        )
        .select_related("marketing_preference")
    )
    recent_cutoff = timezone.now() - timedelta(days=90)
    if campaign.segment == CustomerCampaign.SEGMENT_REPEAT:
        queryset = queryset.filter(order_count__gte=2)
    elif campaign.segment == CustomerCampaign.SEGMENT_RECENT:
        queryset = queryset.filter(last_order_at__gte=recent_cutoff)
    elif campaign.segment == CustomerCampaign.SEGMENT_DORMANT:
        queryset = queryset.filter(last_order_at__lt=recent_cutoff)
    return queryset.order_by("-last_order_at", "name", "id")


def _latest_active_event(
    preference: CustomerMarketingPreference,
    *,
    topic: str,
) -> MarketingConsentEvent | None:
    event = preference.events.order_by("-created_at", "-id").first()
    if event is None or event.action == MarketingConsentEvent.ACTION_WITHDRAWN:
        return None
    if not event.email_marketing or not getattr(event, topic, False):
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

    configured_max = int(getattr(settings, "CUSTOMER_CAMPAIGN_MAX_RECIPIENTS", 100))
    if campaign.max_recipients > configured_max:
        raise CampaignOperationError(
            f"The recipient limit exceeds the configured maximum of {configured_max}."
        )

    campaign.recipients.all().delete()
    recipients = []
    customers = list(eligible_customer_queryset(campaign)[: campaign.max_recipients])
    for customer in customers:
        preference = customer.marketing_preference
        event = _latest_active_event(preference, topic=campaign.topic)
        if event is None:
            continue
        recipients.append(
            CustomerCampaignRecipient(
                campaign=campaign,
                customer=customer,
                email_address=customer.email.strip().lower(),
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
    campaign.approval_note = ""
    campaign.failure_reason = ""
    campaign.started_at = None
    campaign.completed_at = None
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
            "approval_note",
            "failure_reason",
            "started_at",
            "completed_at",
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
    campaign.status = CustomerCampaign.STATUS_APPROVED
    campaign.approved_by = user
    campaign.approved_at = timezone.now()
    campaign.approval_note = (approval_note or "").strip()
    campaign.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
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
    if preference.withdrawn_at is not None or not preference.email_marketing:
        return preference, None, "email_consent_withdrawn"
    if not getattr(preference, recipient.campaign.topic, False):
        return preference, None, "topic_consent_withdrawn"
    event = _latest_active_event(preference, topic=recipient.campaign.topic)
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
    if reason:
        recipient.status = CustomerCampaignRecipient.STATUS_SUPPRESSED
        recipient.suppression_reason = reason
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
        CustomerCampaign.STATUS_FAILED,
    }:
        if unfinished == 0 and campaign.prepared_count:
            campaign.status = CustomerCampaign.STATUS_COMPLETED
            campaign.completed_at = campaign.completed_at or timezone.now()
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
            "updated_at",
        ]
    )
    return campaign


def send_campaign_batch(
    campaign: CustomerCampaign,
    *,
    user,
    batch_size: int | None = None,
) -> CustomerCampaign:
    if not getattr(settings, "CUSTOMER_CAMPAIGN_SEND_ENABLED", False):
        raise CampaignOperationError(
            "Customer campaign sending is disabled by the production safety switch."
        )
    campaign.refresh_from_db()
    if campaign.status not in {
        CustomerCampaign.STATUS_APPROVED,
        CustomerCampaign.STATUS_SENDING,
    }:
        raise CampaignOperationError("The campaign must be approved before sending.")
    if not campaign.approved_by_id or not campaign.approved_at:
        raise CampaignOperationError("The campaign approval record is incomplete.")

    _reconcile_linked_processing(campaign)
    configured_batch = int(getattr(settings, "CUSTOMER_CAMPAIGN_BATCH_SIZE", 10))
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
        retry_outbound_email(log)
        log.refresh_from_db()
        _finalize_delivery(recipient_id, log=log, event=event)

    return refresh_campaign_counts(campaign)


@transaction.atomic
def cancel_campaign(campaign: CustomerCampaign, *, user) -> CustomerCampaign:
    campaign = CustomerCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status in {
        CustomerCampaign.STATUS_COMPLETED,
        CustomerCampaign.STATUS_CANCELLED,
    }:
        raise CampaignOperationError("This campaign can no longer be cancelled.")
    if campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PROCESSING
    ).exists():
        raise CampaignOperationError(
            "A recipient is currently processing. Disable the send switch and review "
            "the delivery evidence before cancelling."
        )
    campaign.recipients.filter(
        status=CustomerCampaignRecipient.STATUS_PENDING
    ).update(
        status=CustomerCampaignRecipient.STATUS_SUPPRESSED,
        suppression_reason="campaign_cancelled",
        attempted_at=timezone.now(),
    )
    campaign.status = CustomerCampaign.STATUS_CANCELLED
    campaign.failure_reason = f"Cancelled by {getattr(user, 'get_username', lambda: 'staff')()}"
    campaign.completed_at = timezone.now()
    campaign.save(
        update_fields=[
            "status",
            "failure_reason",
            "completed_at",
            "updated_at",
        ]
    )
    return refresh_campaign_counts(campaign)
