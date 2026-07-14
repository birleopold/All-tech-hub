import json

from django.utils.safestring import mark_safe

from catalog.models import Product
from commerce import cart as cart_mod
from commerce.models import Order
from core.models import CompanySettings
from growth.models import GrowthSettings
from growth.services import (
    ANALYTICS_SESSION_KEY,
    PURCHASE_SESSION_KEY,
    analytics_event,
    analytics_item,
    purchase_event,
)
from marketing.models import SocialProfileSettings


def _page_analytics_events(request, company) -> list[dict]:
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "url_name", "") or ""
    kwargs = getattr(match, "kwargs", {}) or {}

    if name == "product_detail":
        product = (
            Product.objects.filter(
                slug=kwargs.get("slug"),
                is_published=True,
            )
            .select_related("category")
            .prefetch_related("variants")
            .first()
        )
        if product:
            value = product.min_active_variant_price or product.price
            return [
                analytics_event(
                    "view_item",
                    {
                        "currency": company.currency_code,
                        "value": float(value),
                        "items": [analytics_item(product)],
                    },
                )
            ]

    if name in {"cart", "checkout"}:
        lines = list(cart_mod.iter_cart_lines(request.session))
        if not lines:
            return []
        items = [
            analytics_item(
                line.product,
                variant=line.variant,
                quantity=line.quantity,
            )
            for line in lines
        ]
        subtotal, tax, total, discount = cart_mod.cart_totals_with_discount(
            request.session,
            company.default_tax_rate,
        )
        params = {
            "currency": company.currency_code,
            "value": float(total if name == "checkout" else subtotal),
            "items": items,
        }
        coupon = cart_mod.get_coupon(request.session)
        if coupon:
            params["coupon"] = coupon.code
        if name == "checkout":
            params["tax"] = float(tax)
            params["discount"] = float(discount)
        return [
            analytics_event(
                "begin_checkout" if name == "checkout" else "view_cart",
                params,
            )
        ]

    if name == "order_detail":
        reference = kwargs.get("reference")
        if reference and request.session.get(PURCHASE_SESSION_KEY) == reference:
            order = (
                Order.objects.filter(reference=reference)
                .prefetch_related(
                    "lines__product__category",
                    "lines__product_variant",
                )
                .first()
            )
            if order:
                request.session.pop(PURCHASE_SESSION_KEY, None)
                request.session.modified = True
                return [purchase_event(order)]
    return []


def growth_context(request):
    growth = GrowthSettings.load()
    pending = request.session.pop(ANALYTICS_SESSION_KEY, [])
    if pending:
        request.session.modified = True

    company = CompanySettings.load()
    social = SocialProfileSettings.load()
    same_as = [
        value
        for value in (
            social.facebook_url,
            social.instagram_url,
            social.tiktok_url,
            social.x_url,
            social.linkedin_url,
            social.youtube_url,
            growth.google_business_profile_url,
        )
        if value
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "ComputerStore",
        "name": company.legal_name or company.company_name,
        "url": company.website or request.build_absolute_uri("/"),
    }
    if company.logo:
        schema["logo"] = request.build_absolute_uri(company.logo.url)
    if company.phone:
        schema["telephone"] = company.phone
    if company.email:
        schema["email"] = company.email
    if growth.google_place_id:
        schema["identifier"] = growth.google_place_id
    if growth.google_business_profile_url:
        schema["hasMap"] = growth.google_business_profile_url
    if same_as:
        schema["sameAs"] = same_as
    if company.address_line or company.city or company.country:
        schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": company.address_line,
            "addressLocality": company.city,
            "addressRegion": company.region,
            "postalCode": company.postal_code,
            "addressCountry": company.country,
        }

    return {
        "growth_settings": growth,
        "analytics_pending_events": pending if isinstance(pending, list) else [],
        "analytics_page_events": _page_analytics_events(request, company),
        "local_business_schema_json": mark_safe(
            json.dumps(schema, separators=(",", ":")).replace("</", "<\\/")
        ),
    }
