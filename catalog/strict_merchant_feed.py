from xml.etree import ElementTree as ET

from django.http import HttpResponse
from django.views.decorators.http import require_GET

from catalog.seo_feeds import GOOGLE_NS, google_merchant_feed as base_google_merchant_feed


@require_GET
def strict_google_merchant_feed(request):
    """Correct identifier_exists using manufacturer identifiers, not merchant SKUs."""

    response = base_google_merchant_feed(request)
    root = ET.fromstring(response.content)
    namespace = {"g": GOOGLE_NS}

    for item in root.findall("./channel/item"):
        gtin = item.find("g:gtin", namespace)
        mpn = item.find("g:mpn", namespace)
        brand = item.find("g:brand", namespace)
        identifier = item.find("g:identifier_exists", namespace)
        if identifier is None:
            identifier = ET.SubElement(item, f"{{{GOOGLE_NS}}}identifier_exists")

        has_gtin = bool(gtin is not None and (gtin.text or "").strip())
        has_brand_mpn = bool(
            brand is not None
            and (brand.text or "").strip()
            and mpn is not None
            and (mpn.text or "").strip()
        )
        identifier.text = "yes" if has_gtin or has_brand_mpn else "no"

    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    corrected = HttpResponse(
        payload,
        content_type="application/rss+xml; charset=utf-8",
    )
    corrected["Cache-Control"] = response.get("Cache-Control", "public, max-age=3600")
    corrected["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return corrected
