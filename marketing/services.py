from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from core.models import CompanySettings, ContactMessage
from core.notifications import staff_notify
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
