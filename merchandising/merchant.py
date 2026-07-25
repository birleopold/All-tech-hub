from __future__ import annotations

from xml.etree import ElementTree as ET

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from catalog.seo_feeds import GOOGLE_NS
from catalog.strict_merchant_feed import strict_google_merchant_feed as base_strict_feed
from merchandising.models import ProductCommerceProfile


@require_GET
def strict_google_merchant_feed(request):
    """Optionally remove products that have not passed an explicit data review."""

    response = base_strict_feed(request)
    if not getattr(settings, "MERCHANT_STRICT_READINESS", False):
        response["X-Merchant-Readiness"] = "audit-only"
        return response

    try:
        profiles = (
            ProductCommerceProfile.objects.filter(merchant_enabled=True)
            .select_related("product", "product__growth_data", "product__category")
            .prefetch_related("product__gallery_images", "product__variants")
        )
        eligible: dict[str, ProductCommerceProfile] = {}
        for profile in profiles:
            if not profile.is_merchant_ready:
                continue
            product = profile.product
            variants = [variant for variant in product.variants.all() if variant.is_active]
            if variants:
                for variant in variants:
                    item_id = variant.sku or f"LEOSOFT-{product.pk}-{variant.pk}"
                    eligible[item_id] = profile
            else:
                item_id = product.sku or f"LEOSOFT-{product.pk}"
                eligible[item_id] = profile
    except (OperationalError, ProgrammingError):
        response["X-Merchant-Readiness"] = "schema-unavailable"
        return response

    root = ET.fromstring(response.content)
    namespace = {"g": GOOGLE_NS}
    channel = root.find("./channel")
    removed = 0
    kept = 0
    if channel is not None:
        for item in list(channel.findall("item")):
            identifier = item.find("g:id", namespace)
            item_id = (identifier.text or "").strip() if identifier is not None else ""
            profile = eligible.get(item_id)
            if profile is None:
                channel.remove(item)
                removed += 1
                continue
            kept += 1
            shipping = item.find("g:shipping", namespace)
            if shipping is not None:
                price = shipping.find("g:price", namespace)
                if price is not None:
                    currency = profile.product.price.currency if hasattr(profile.product.price, "currency") else "UGX"
                    value = 0 if profile.merchant_free_shipping else profile.merchant_shipping_price
                    price.text = f"{value or 0:.2f} {currency}"

    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    corrected = HttpResponse(payload, content_type="application/rss+xml; charset=utf-8")
    corrected["Cache-Control"] = response.get("Cache-Control", "public, max-age=3600")
    corrected["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    corrected["X-Merchant-Readiness"] = "strict"
    corrected["X-Merchant-Eligible-Items"] = str(kept)
    corrected["X-Merchant-Excluded-Items"] = str(removed)
    return corrected
