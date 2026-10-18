from __future__ import annotations

from xml.etree import ElementTree as ET

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from catalog.seo_feeds import GOOGLE_NS
from catalog.strict_merchant_feed import strict_google_merchant_feed as base_strict_feed
from core.models import CompanySettings
from merchandising.models import ProductCommerceProfile


def _build_google_merchant_feed(request, *, require_approval=False):
    """Use the existing RSS exporter but never export unapproved items when requested."""

    response = base_strict_feed(request)
    if not require_approval and not getattr(settings, "MERCHANT_STRICT_READINESS", False):
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
                    # Approval of a parent must not publish a sold-out SKU.
                    # Untracked variants require separate stock verification;
                    # this feed cannot infer availability for them.
                    if not variant.track_inventory or variant.stock_quantity <= 0:
                        continue
                    item_id = variant.sku or f"LEOSOFT-{product.pk}-{variant.pk}"
                    eligible[item_id] = profile
            elif product.track_inventory and product.stock_quantity > 0:
                item_id = product.sku or f"LEOSOFT-{product.pk}"
                eligible[item_id] = profile
    except (OperationalError, ProgrammingError):
        # A broken approval schema cannot be treated as permission to export
        # all unreviewed products. Try again after the database is repaired.
        response = HttpResponse(
            "Merchant readiness is temporarily unavailable.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
        response["Cache-Control"] = "no-store"
        response["Retry-After"] = "300"
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["X-Merchant-Readiness"] = "schema-unavailable"
        return response

    company = CompanySettings.load()
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
                    value = 0 if profile.merchant_free_shipping else profile.merchant_shipping_price
                    price.text = f"{value or 0:.2f} {company.currency_code}"

    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    corrected = HttpResponse(payload, content_type="application/rss+xml; charset=utf-8")
    corrected["Cache-Control"] = response.get("Cache-Control", "public, max-age=3600")
    corrected["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    corrected["X-Merchant-Readiness"] = "strict"
    corrected["X-Merchant-Eligible-Items"] = str(kept)
    corrected["X-Merchant-Excluded-Items"] = str(removed)
    return corrected


@require_GET
def strict_google_merchant_feed(request):
    """Legacy URL: retain configured readiness behavior for existing consumers."""
    return _build_google_merchant_feed(request)


@require_GET
def approved_google_merchant_feed(request):
    """Google scheduled-fetch source; always requires verified staff approval.

    This safe endpoint is intentionally independent of the legacy
    MERCHANT_STRICT_READINESS environment flag. Empty is preferable to
    advertising unverified prices, stock, shipping, or condition.
    """
    return _build_google_merchant_feed(request, require_approval=True)
