from catalog.models import Product
from commerce import cart as cart_mod
from commerce.models import Order
from core.models import CompanySettings
from core.seo import html_language, og_locale, public_url, script_safe_json
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


def _organization_schema(request, company, growth, social) -> str:
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") or ""
    if url_name not in {"home", "about", "contact", "buying_guide"}:
        return ""

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
    home_url = public_url("/")
    schema = {
        "@context": "https://schema.org",
        "@type": ["OnlineStore", "ComputerStore"],
        "@id": f"{home_url}#organization",
        "name": company.legal_name or company.company_name,
        "alternateName": company.company_name,
        "url": home_url,
        "description": company.tagline or "Technology products, repairs and professional IT support.",
        "areaServed": {
            "@type": "Country",
            "name": company.country or "Uganda",
        },
        "currenciesAccepted": company.currency_code,
        "knowsAbout": [
            "Computers",
            "Laptops",
            "Computer accessories",
            "Computer repair",
            "IT installation",
            "Business IT support",
        ],
    }
    if company.logo:
        schema["logo"] = public_url(company.logo.url)
        schema["image"] = public_url(company.logo.url)
    if company.phone or company.email:
        contact_point = {
            "@type": "ContactPoint",
            "contactType": "customer service",
            "availableLanguage": [growth.merchant_language or "en"],
            "areaServed": growth.merchant_country or "UG",
        }
        if company.phone:
            contact_point["telephone"] = company.phone
            schema["telephone"] = company.phone
        if company.email:
            contact_point["email"] = company.email
            schema["email"] = company.email
        schema["contactPoint"] = contact_point
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
            "addressCountry": company.country or growth.merchant_country,
        }
    if growth.merchant_return_policy_url:
        schema["hasMerchantReturnPolicy"] = {
            "@type": "MerchantReturnPolicy",
            "merchantReturnLink": growth.merchant_return_policy_url,
        }
    if growth.merchant_shipping_service:
        schema["hasShippingService"] = {
            "@type": "ShippingService",
            "@id": f"{home_url}#shipping-policy",
            "name": growth.merchant_shipping_service,
            "fulfillmentType": "https://schema.org/FulfillmentTypeDelivery",
            "shippingConditions": {
                "@type": "ShippingConditions",
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": growth.merchant_country,
                },
                "shippingRate": {
                    "@type": "MonetaryAmount",
                    "value": str(growth.merchant_shipping_price),
                    "currency": company.currency_code,
                },
            },
        }
    return script_safe_json(schema)


def growth_context(request):
    growth = GrowthSettings.load()
    pending = request.session.pop(ANALYTICS_SESSION_KEY, [])
    if pending:
        request.session.modified = True

    company = CompanySettings.load()
    social = SocialProfileSettings.load()
    return {
        "growth_settings": growth,
        "analytics_pending_events": pending if isinstance(pending, list) else [],
        "analytics_page_events": _page_analytics_events(request, company),
        "local_business_schema_json": _organization_schema(
            request,
            company,
            growth,
            social,
        ),
        "seo_html_language": html_language(
            growth.merchant_language,
            growth.merchant_country,
        ),
        "seo_og_locale": og_locale(
            growth.merchant_language,
            growth.merchant_country,
        ),
    }
