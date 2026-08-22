from datetime import timedelta
from decimal import Decimal
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from billing.models import CommercialDocument, CommercialLine, allocate_document_number
from core.models import CompanySettings, ContactMessage
from core.notifications import staff_notify
from crm.models import Customer
from marketing.attribution import order_attribution
from marketing.lead_policy import classify_enquiry, response_minutes
from marketing.models import (
    CampaignLink,
    CaptionTemplate,
    MarketingCampaign,
    MarketingLead,
)


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def product_public_url(product: Product) -> str:
    company = CompanySettings.load()
    base = (company.website or "https://leosoftug.com").rstrip("/") + "/"
    return urljoin(base, product.get_absolute_url().lstrip("/"))


def render_caption(
    template: CaptionTemplate,
    product: Product | None = None,
    url: str = "",
) -> str:
    company = CompanySettings.load()
    price = ""
    currency = company.currency_code
    category = ""
    product_name = ""
    if product:
        product_name = product.name
        category = product.category.name
        value = product.min_active_variant_price or product.price
        price = f"{value}"
        url = url or product_public_url(product)

    values = _SafeFormatDict(
        product_name=product_name,
        price=price,
        currency=currency,
        category=category,
        url=url,
        company=company.company_name,
        hashtags=template.hashtags,
    )
    return template.body.format_map(values).strip()


def _available_sales_owner():
    user_model = get_user_model()
    return (
        user_model.objects.filter(is_active=True, is_staff=True)
        .filter(
            Q(is_superuser=True)
            | Q(groups__name__in=("Sales", "Manager"))
            | Q(
                user_permissions__content_type__app_label="marketing",
                user_permissions__codename="change_marketinglead",
            )
        )
        .annotate(
            active_lead_count=Count(
                "assigned_marketing_leads",
                filter=Q(
                    assigned_marketing_leads__status__in=(
                        MarketingLead.STATUS_NEW,
                        MarketingLead.STATUS_CONTACTED,
                        MarketingLead.STATUS_QUALIFIED,
                    )
                ),
                distinct=True,
            )
        )
        .distinct()
        .order_by("active_lead_count", "pk")
        .first()
    )


def _notify_new_lead(lead: MarketingLead) -> None:
    destination = reverse("staff_marketing_lead_edit", kwargs={"pk": lead.pk})
    message = (
        f"New {lead.get_priority_display().lower()}-priority {lead.request_type} "
        f"enquiry from {lead.name} ({lead.source})"
    )
    if lead.assigned_to:
        staff_notify(lead.assigned_to, message, destination)
        return
    user_model = get_user_model()
    fallback = (
        user_model.objects.filter(is_active=True, is_staff=True)
        .filter(Q(is_superuser=True) | Q(groups__name="Manager"))
        .distinct()
        .order_by("pk")[:5]
    )
    for user in fallback:
        staff_notify(user, f"Unassigned sales lead: {message}", destination)


@transaction.atomic
def create_lead_from_contact(request, contact_message, *, product=None) -> MarketingLead:
    verified = order_attribution(request.session)
    link = None
    campaign = None

    link = verified.get("marketing_link")
    if link:
        campaign = link.campaign
        product = product or link.product

    if not campaign and verified.get("marketing_campaign"):
        campaign = MarketingCampaign.objects.filter(
            slug=verified["marketing_campaign"]
        ).first()

    content = verified.get("marketing_content", "")
    if not product and content:
        product = Product.objects.filter(slug=content, is_published=True).first()
    if product and not contact_message.product_id:
        contact_message.product = product
        contact_message.save(update_fields=["product"])

    request_type, priority = classify_enquiry(
        contact_message.request_type or request.POST.get("request_type")
    )
    existing = MarketingLead.objects.filter(
        contact_message_id=contact_message.pk
    ).first()
    due_at = timezone.now() + timedelta(
        minutes=response_minutes(
            priority,
            getattr(settings, "MARKETING_LEAD_RESPONSE_TARGET_MINUTES", 30),
        )
    )
    owner = existing.assigned_to if existing and existing.assigned_to_id else _available_sales_owner()
    lead, created = MarketingLead.objects.update_or_create(
        contact_message_id=contact_message.pk,
        defaults={
            "campaign": campaign,
            "link": link,
            "product": product,
            "name": contact_message.name,
            "email": contact_message.email,
            "phone": contact_message.phone,
            "source": verified.get("marketing_source") or "direct",
            "medium": verified.get("marketing_medium") or "website",
            "request_type": request_type,
            "priority": priority,
            "assigned_to": owner,
            "response_due_at": existing.response_due_at if existing else due_at,
            "next_follow_up_at": (
                existing.next_follow_up_at if existing else due_at
            ),
            "estimated_value": (
                existing.estimated_value
                if existing
                else (product.price if product else 0)
            ),
            "notes": f"{contact_message.subject}\n\n{contact_message.message}".strip(),
        },
    )
    if created and link:
        CampaignLink.objects.filter(pk=link.pk).update(lead_count=F("lead_count") + 1)
    if created:
        _notify_new_lead(lead)

    from growth.services import attribute_lead_to_ambassador, queue_analytics_event

    attribute_lead_to_ambassador(request, lead)
    company = CompanySettings.load()
    queue_analytics_event(
        request,
        "generate_lead",
        {
            "currency": company.currency_code,
            "value": float(lead.estimated_value or 0),
            "lead_source": lead.source,
            "lead_medium": lead.medium,
        },
    )
    return lead


@transaction.atomic
def close_lead_from_order(order) -> MarketingLead | None:
    """Close the most relevant open enquiry when its customer completes checkout."""
    candidates = MarketingLead.objects.select_for_update().filter(
        email__iexact=order.contact_email,
        status__in=(
            MarketingLead.STATUS_NEW,
            MarketingLead.STATUS_CONTACTED,
            MarketingLead.STATUS_QUALIFIED,
        ),
        won_order__isnull=True,
    ).order_by("-created_at", "-pk")
    lead = None
    if order.marketing_link_id:
        lead = candidates.filter(link_id=order.marketing_link_id).first()
    if lead is None:
        lead = candidates.first()
    if lead is None:
        return None
    lead.status = MarketingLead.STATUS_WON
    lead.won_order = order
    fields = ["status", "won_order", "updated_at"]
    if not lead.estimated_value:
        lead.estimated_value = order.total
        fields.append("estimated_value")
    lead.save(update_fields=fields)
    if lead.contact_message_id:
        ContactMessage.objects.filter(pk=lead.contact_message_id).update(handled=True)
    return lead


@transaction.atomic
def create_quote_from_lead(lead: MarketingLead, *, actor) -> CommercialDocument:
    """Create one editable, correctly linked commercial quotation per enquiry."""
    lead = MarketingLead.objects.select_for_update().select_related(
        "product", "quoted_document"
    ).get(pk=lead.pk)
    if lead.quoted_document_id:
        return lead.quoted_document
    if lead.status in {MarketingLead.STATUS_WON, MarketingLead.STATUS_LOST}:
        raise ValueError("Closed enquiries cannot be converted into new quotations.")

    customer = None
    if lead.email:
        customer = Customer.objects.filter(email__iexact=lead.email).order_by("pk").first()
        if customer is None:
            customer = Customer.objects.create(name=lead.name, email=lead.email, phone=lead.phone)
    company = CompanySettings.load()
    document = CommercialDocument.objects.create(
        doc_type=CommercialDocument.TYPE_QUOTE,
        number=allocate_document_number(CommercialDocument.PREFIX[CommercialDocument.TYPE_QUOTE]),
        customer=customer,
        customer_name=lead.name,
        customer_email=lead.email,
        customer_phone=lead.phone,
        title=(f"Quotation for {lead.product.name}" if lead.product_id else "Customer quotation"),
        notes=lead.notes,
        tax_rate=company.default_tax_rate,
        created_by=actor,
        salesperson=lead.assigned_to or actor,
    )
    if lead.product_id:
        CommercialLine.objects.create(
            document=document,
            product=lead.product,
            description=lead.product.name,
            quantity=Decimal("1"),
            unit_price=lead.product.min_active_variant_price or lead.product.price,
            source_type=(
                CommercialLine.SOURCE_STOCK
                if lead.product.kind == Product.KIND_PHYSICAL
                else CommercialLine.SOURCE_SERVICE
            ),
            tax_rate=company.default_tax_rate,
        )
        document.recalculate_from_lines()
        document.save()
    lead.quoted_document = document
    lead.status = MarketingLead.STATUS_QUALIFIED
    lead.estimated_value = document.total or lead.estimated_value
    if not lead.assigned_to_id:
        lead.assigned_to = actor
    lead.save()
    if lead.contact_message_id:
        ContactMessage.objects.filter(pk=lead.contact_message_id).update(handled=True)
    return document


def process_due_lead_followups(*, limit: int = 100, dry_run: bool = False) -> dict:
    """Remind assigned staff and escalate unanswered enquiries once to managers."""
    now = timezone.now()
    reminder_interval = max(5, int(getattr(settings, "MARKETING_LEAD_REMINDER_INTERVAL_MINUTES", 60)))
    escalation_delay = max(0, int(getattr(settings, "MARKETING_LEAD_ESCALATION_MINUTES", 30)))
    throttle_before = now - timedelta(minutes=reminder_interval)
    candidates = MarketingLead.objects.select_related("assigned_to").filter(
        status__in=(MarketingLead.STATUS_NEW, MarketingLead.STATUS_CONTACTED, MarketingLead.STATUS_QUALIFIED)
    ).filter(
        Q(next_follow_up_at__lte=now)
        | Q(status=MarketingLead.STATUS_NEW, first_contacted_at__isnull=True, response_due_at__lte=now)
    ).filter(Q(last_reminded_at__isnull=True) | Q(last_reminded_at__lte=throttle_before)).order_by(
        "response_due_at", "next_follow_up_at", "pk"
    )[:max(1, min(int(limit), 500))]
    reminders = escalations = 0
    for lead in candidates:
        destination = reverse("staff_marketing_lead_edit", kwargs={"pk": lead.pk})
        should_escalate = bool(
            lead.status == MarketingLead.STATUS_NEW
            and lead.response_due_at
            and lead.response_due_at <= now - timedelta(minutes=escalation_delay)
            and not lead.escalated_at
        )
        reminders += 1
        escalations += int(should_escalate)
        if dry_run:
            continue
        if lead.assigned_to_id:
            staff_notify(lead.assigned_to, f"Sales follow-up overdue: {lead.name}", destination)
        if should_escalate:
            managers = get_user_model().objects.filter(is_active=True, is_staff=True).filter(
                Q(is_superuser=True) | Q(groups__name="Manager")
            ).exclude(pk=lead.assigned_to_id).distinct()[:10]
            for manager in managers:
                staff_notify(manager, f"Escalated unanswered enquiry: {lead.name}", destination)
            lead.escalated_at = now
        lead.last_reminded_at = now
        lead.save(update_fields=["last_reminded_at", "escalated_at", "updated_at"])
    return {"reminded": reminders, "escalated": escalations}
