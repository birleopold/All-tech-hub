from __future__ import annotations

from xml.etree import ElementTree as ET

from django.db import OperationalError, ProgrammingError
from django.db.models import Max
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from catalog import seo_feeds
from core.seo import public_url
from merchandising.models import BuyingGuide, CommercialLandingPage, DeliveryZone
from merchandising.views import commercial_page_path


@require_GET
def sitemap_index(request):
    """Extend the established sitemap index with commercial and editorial URLs."""

    response = seo_feeds.sitemap_index(request)
    root = ET.fromstring(response.content)
    locations = {
        (node.text or "").strip()
        for node in root.findall(f".//{{{seo_feeds.SITEMAP_NS}}}loc")
    }
    commercial_url = public_url(reverse("commercial_sitemap"))
    if commercial_url not in locations:
        sitemap = ET.SubElement(root, f"{{{seo_feeds.SITEMAP_NS}}}sitemap")
        ET.SubElement(sitemap, f"{{{seo_feeds.SITEMAP_NS}}}loc").text = commercial_url
        try:
            page_update = CommercialLandingPage.objects.filter(is_published=True).aggregate(value=Max("updated_at"))["value"]
            guide_update = BuyingGuide.objects.filter(is_published=True).aggregate(value=Max("updated_at"))["value"]
            latest = max((value for value in (page_update, guide_update) if value), default=None)
        except (OperationalError, ProgrammingError):
            latest = None
        if latest:
            ET.SubElement(sitemap, f"{{{seo_feeds.SITEMAP_NS}}}lastmod").text = latest.isoformat(timespec="seconds")
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    corrected = HttpResponse(payload, content_type="application/xml; charset=utf-8")
    corrected["Cache-Control"] = response.get("Cache-Control", "public, max-age=3600")
    return corrected


@require_GET
def commercial_sitemap(request):
    root = ET.Element(f"{{{seo_feeds.SITEMAP_NS}}}urlset")
    try:
        pages = CommercialLandingPage.objects.filter(is_published=True).order_by("pk")
        guides = BuyingGuide.objects.filter(is_published=True).order_by("pk")
        for page in pages:
            seo_feeds._add_url(root, public_url(commercial_page_path(page.slug)), page.updated_at)
        seo_feeds._add_url(root, public_url(reverse("buying_guide_list")))
        for guide in guides:
            seo_feeds._add_url(root, public_url(guide.get_absolute_url()), guide.updated_at)
        if DeliveryZone.objects.filter(is_active=True).exists():
            seo_feeds._add_url(root, public_url(reverse("delivery_zones")))
    except (OperationalError, ProgrammingError):
        pass
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    response = HttpResponse(payload, content_type="application/xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response
