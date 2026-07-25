from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Max, Q
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from catalog.models import Category, Product
from catalog.public_views import PublicProductListView
from core.models import CompanySettings
from core.seo import clean_text, meta_description, public_url
from growth.models import GrowthSettings, ProductGrowthData

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
GOOGLE_NS = "http://base.google.com/ns/1.0"
ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("image", IMAGE_NS)
ET.register_namespace("g", GOOGLE_NS)


def _xml_response(root: ET.Element, *, content_type: str = "application/xml") -> HttpResponse:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    response = HttpResponse(payload, content_type=f"{content_type}; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def _date_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.isoformat(timespec="seconds")
    return str(value)


def _latest_product_update():
    return Product.objects.filter(is_published=True).aggregate(value=Max("updated_at"))["value"]


def _add_url(root: ET.Element, location: str, lastmod=None) -> ET.Element:
    node = ET.SubElement(root, f"{{{SITEMAP_NS}}}url")
    ET.SubElement(node, f"{{{SITEMAP_NS}}}loc").text = location
    if lastmod:
        ET.SubElement(node, f"{{{SITEMAP_NS}}}lastmod").text = _date_text(lastmod)
    return node


@require_GET
def sitemap_index(request):
    root = ET.Element(f"{{{SITEMAP_NS}}}sitemapindex")
    lastmod = _latest_product_update()
    sections = ("static", "products", "categories", "collections", "brands")
    for section in sections:
        sitemap = ET.SubElement(root, f"{{{SITEMAP_NS}}}sitemap")
        ET.SubElement(sitemap, f"{{{SITEMAP_NS}}}loc").text = public_url(
            reverse("seo_sitemap", args=[section])
        )
        if lastmod:
            ET.SubElement(sitemap, f"{{{SITEMAP_NS}}}lastmod").text = _date_text(lastmod)
    image_map = ET.SubElement(root, f"{{{SITEMAP_NS}}}sitemap")
    ET.SubElement(image_map, f"{{{SITEMAP_NS}}}loc").text = public_url(
        reverse("image_sitemap")
    )
    if lastmod:
        ET.SubElement(image_map, f"{{{SITEMAP_NS}}}lastmod").text = _date_text(lastmod)
    return _xml_response(root)


@require_GET
def seo_sitemap(request, section: str):
    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    latest = _latest_product_update()

    if section == "static":
        for name in (
            "home",
            "product_list",
            "physical_product_list",
            "service_list",
            "buying_guide",
            "about",
            "contact",
        ):
            _add_url(root, public_url(reverse(name)), latest)
    elif section == "products":
        for product in Product.objects.filter(is_published=True).only(
            "slug", "updated_at"
        ).order_by("pk"):
            _add_url(root, public_url(product.get_absolute_url()), product.updated_at)
    elif section == "categories":
        categories = (
            Category.objects.annotate(
                direct_count=Count(
                    "products",
                    filter=Q(products__is_published=True),
                    distinct=True,
                ),
                child_count=Count(
                    "subcategories__products",
                    filter=Q(subcategories__products__is_published=True),
                    distinct=True,
                ),
            )
            .filter(Q(direct_count__gt=0) | Q(child_count__gt=0))
            .order_by("pk")
        )
        for category in categories:
            _add_url(
                root,
                public_url(reverse("product_category", args=[category.slug])),
                latest,
            )
    elif section == "collections":
        for slug in PublicProductListView.COLLECTIONS:
            _add_url(
                root,
                public_url(reverse("product_collection", args=[slug])),
                latest,
            )
    elif section == "brands":
        brands = (
            ProductGrowthData.objects.filter(product__is_published=True)
            .exclude(brand="")
            .values("brand")
            .annotate(updated=Max("updated_at"))
            .order_by("brand")
        )
        seen = set()
        for row in brands:
            brand_slug = slugify(row["brand"])
            if not brand_slug or brand_slug in seen:
                continue
            seen.add(brand_slug)
            _add_url(
                root,
                public_url(reverse("product_brand", args=[brand_slug])),
                row["updated"],
            )
    else:
        raise Http404("Unknown sitemap section")
    return _xml_response(root)


@require_GET
def image_sitemap(request):
    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    products = (
        Product.objects.filter(is_published=True)
        .prefetch_related("gallery_images")
        .order_by("pk")
    )
    for product in products:
        images: list[tuple[str, str]] = []
        if product.image:
            images.append((public_url(product.image.url), product.name))
        known_urls = {item[0] for item in images}
        for position, gallery in enumerate(product.gallery_images.all(), start=1):
            if not gallery.image:
                continue
            title = clean_text(gallery.alt_text) or f"{product.name} image {position}"
            image_url = public_url(gallery.image.url)
            if image_url not in known_urls:
                images.append((image_url, title))
                known_urls.add(image_url)
        if not images:
            continue
        url_node = _add_url(root, public_url(product.get_absolute_url()), product.updated_at)
        for image_url, title in images:
            image_node = ET.SubElement(url_node, f"{{{IMAGE_NS}}}image")
            ET.SubElement(image_node, f"{{{IMAGE_NS}}}loc").text = image_url
            ET.SubElement(image_node, f"{{{IMAGE_NS}}}title").text = title
    return _xml_response(root)


def _g(parent: ET.Element, name: str, value) -> None:
    if value is None or value == "":
        return
    ET.SubElement(parent, f"{{{GOOGLE_NS}}}{name}").text = str(value)


def _product_image(product) -> str:
    image = product.primary_display_image
    return public_url(image.url) if image else ""


def _condition(metadata) -> str:
    value = getattr(metadata, "condition", "") or ProductGrowthData.CONDITION_NEW
    return value if value in {"new", "refurbished", "used"} else "new"


def _append_merchant_item(
    channel: ET.Element,
    *,
    product,
    metadata,
    company,
    growth,
    item_id: str,
    title: str,
    link: str,
    price,
    available: bool,
    variant=None,
):
    clean_title = clean_text(title)[:150]
    description = meta_description(
        product.short_description or product.description,
        fallback=f"{product.category.name} available from {company.company_name}.",
        limit=5000,
    )
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = clean_title
    ET.SubElement(item, "link").text = link
    ET.SubElement(item, "description").text = description
    _g(item, "id", item_id)
    _g(item, "title", clean_title)
    _g(item, "description", description)
    _g(item, "link", link)
    _g(item, "image_link", _product_image(product))
    _g(item, "availability", "in_stock" if available else "out_of_stock")
    _g(item, "price", f"{price:.2f} {company.currency_code}")
    _g(item, "condition", _condition(metadata))
    _g(item, "product_type", product.category.name)
    if metadata:
        _g(item, "brand", metadata.brand)
        _g(item, "google_product_category", metadata.google_product_category)
        _g(item, "custom_label_0", metadata.custom_label_0)
        _g(item, "shipping_label", metadata.shipping_label)
    if variant is not None:
        _g(item, "item_group_id", product.sku or f"LEOSOFT-{product.pk}")
        _g(item, "mpn", metadata.mpn if metadata else "")
        _g(
            item,
            "identifier_exists",
            "yes" if variant.sku or (metadata and metadata.mpn) else "no",
        )
    else:
        _g(item, "gtin", metadata.gtin if metadata else "")
        _g(item, "mpn", metadata.mpn if metadata else "")
        identifiers = bool(product.sku or (metadata and (metadata.gtin or metadata.mpn)))
        _g(item, "identifier_exists", "yes" if identifiers else "no")
    shipping = ET.SubElement(item, f"{{{GOOGLE_NS}}}shipping")
    _g(shipping, "country", growth.merchant_country)
    _g(shipping, "service", growth.merchant_shipping_service)
    _g(shipping, "price", f"{growth.merchant_shipping_price:.2f} {company.currency_code}")


@require_GET
def google_merchant_feed(request):
    company = CompanySettings.load()
    growth = GrowthSettings.load()
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"{company.company_name} product feed"
    ET.SubElement(channel, "link").text = public_url(reverse("physical_product_list"))
    ET.SubElement(channel, "description").text = (
        f"Published physical technology products from {company.company_name}."
    )

    products = (
        Product.objects.filter(is_published=True, kind=Product.KIND_PHYSICAL)
        .select_related("category", "growth_data")
        .prefetch_related("gallery_images", "variants")
        .order_by("pk")
    )
    for product in products:
        if not _product_image(product):
            continue
        try:
            metadata = product.growth_data
        except ObjectDoesNotExist:
            metadata = None
        active_variants = [variant for variant in product.variants.all() if variant.is_active]
        if active_variants:
            for variant in active_variants:
                item_id = variant.sku or f"LEOSOFT-{product.pk}-{variant.pk}"
                _append_merchant_item(
                    channel,
                    product=product,
                    metadata=metadata,
                    company=company,
                    growth=growth,
                    item_id=item_id,
                    title=f"{product.name} — {variant.name}",
                    link=public_url(product.get_absolute_url(), {"variant": variant.pk}),
                    price=variant.price,
                    available=variant.available_to_sell,
                    variant=variant,
                )
        else:
            _append_merchant_item(
                channel,
                product=product,
                metadata=metadata,
                company=company,
                growth=growth,
                item_id=product.sku or f"LEOSOFT-{product.pk}",
                title=product.name,
                link=public_url(product.get_absolute_url()),
                price=product.price,
                available=product.available_to_sell,
            )

    response = _xml_response(rss, content_type="application/rss+xml")
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
