"""Product-specific ordering links using the existing business contact settings."""

from urllib.parse import urlencode

from django import template

from core.seo import public_url
from marketing.lead_policy import uganda_whatsapp_digits

register = template.Library()


@register.simple_tag(takes_context=True)
def product_order_links(context, product):
    company = context.get("company")
    profiles = context.get("social_profiles")
    phone = uganda_whatsapp_digits(getattr(company, "phone", ""))
    whatsapp = uganda_whatsapp_digits(getattr(profiles, "whatsapp_number", ""))
    links = {
        "call_url": f"tel:+{phone}" if phone else "",
        "whatsapp_url": "",
    }
    if whatsapp:
        action = "book" if product.kind == "service" else "order"
        company_name = getattr(company, "company_name", "") or "LEOSOFT"
        message = (
            f"Hello {company_name}, I would like to {action} {product.name}.\n"
            "Please confirm the price, availability and delivery or collection options.\n"
            f"{public_url(product.get_absolute_url())}"
        )
        links["whatsapp_url"] = f"https://wa.me/{whatsapp}?{urlencode({'text': message})}"
    return links
