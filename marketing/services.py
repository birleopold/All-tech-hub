from urllib.parse import urljoin

from django.db.models import F

from catalog.models import Product
from core.models import CompanySettings
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


def create_lead_from_contact(request, contact_message) -> MarketingLead:
    attribution = request.session.get("marketing_attribution", {}) or {}
    link = None
    campaign = None
    product = None

    link_id = attribution.get("link_id")
    if link_id:
        link = CampaignLink.objects.select_related("campaign", "product").filter(
            pk=link_id
        ).first()
        if link:
            campaign = link.campaign
            product = link.product

    if not campaign and attribution.get("campaign"):
        campaign = MarketingCampaign.objects.filter(
            slug=attribution["campaign"]
        ).first()

    content = attribution.get("content", "")
    if not product and content:
        product = Product.objects.filter(slug=content, is_published=True).first()

    lead, created = MarketingLead.objects.update_or_create(
        contact_message_id=contact_message.pk,
        defaults={
            "campaign": campaign,
            "link": link,
            "product": product,
            "name": contact_message.name,
            "email": contact_message.email,
            "phone": contact_message.phone,
            "source": attribution.get("source") or "direct",
            "medium": attribution.get("medium") or "website",
            "notes": f"{contact_message.subject}\n\n{contact_message.message}".strip(),
        },
    )
    if created and link:
        CampaignLink.objects.filter(pk=link.pk).update(lead_count=F("lead_count") + 1)

    from growth.services import attribute_lead_to_ambassador

    attribute_lead_to_ambassador(request, lead)
    return lead
