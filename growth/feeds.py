import csv
from xml.etree import ElementTree as ET

from django.http import HttpResponse, JsonResponse

from catalog.models import Product
from core.models import CompanySettings
from growth.models import GrowthSettings

GOOGLE_NS = "http://base.google.com/ns/1.0"


def _clean(value, limit: int = 5000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _metadata(product):
    try:
        return product.growth_data
    except Exception:
        return None


def _base_product_data(request, product, config):
    metadata = _metadata(product)
    image = product.primary_display_image
    additional_images = [
        request.build_absolute_uri(row.image.url)
        for row in product.gallery_images.all()
        if row.image and (not image or row.image.name != image.name)
    ][:10]
    brand = (metadata.brand if metadata else "") or config.merchant_default_brand
    gtin = metadata.gtin if metadata else ""
    mpn = metadata.mpn if metadata else ""
    identifier_exists = "yes" if gtin or (brand and mpn) else "no"
    description = _clean(
        product.short_description
        or product.description
        or f"{product.name} from LEOSOFT UG LTD.",
        5000,
    )
    return {
        "description": description,
        "link": request.build_absolute_uri(product.get_absolute_url()),
        "image_link": request.build_absolute_uri(image.url) if image else "",
        "additional_image_link": additional_images,
        "condition": metadata.condition if metadata else "new",
        "brand": brand,
        "gtin": gtin,
        "mpn": mpn,
        "identifier_exists": identifier_exists,
        "google_product_category": metadata.google_product_category if metadata else "",
        "product_type": product.category.name,
        "custom_label_0": metadata.custom_label_0 if metadata else "",
        "shipping_label": metadata.shipping_label if metadata else "",
    }


def merchant_rows(request):
    config = GrowthSettings.load()
    company = CompanySettings.load()
    products = (
        Product.objects.filter(
            is_published=True,
            kind=Product.KIND_PHYSICAL,
        )
        .select_related("category", "growth_data")
        .prefetch_related("gallery_images", "variants")
        .order_by("name")
    )
    currency = company.currency_code
    for product in products:
        base = _base_product_data(request, product, config)
        active_variants = [v for v in product.variants.all() if v.is_active]
        if active_variants:
            group_id = product.sku or f"product-{product.pk}"
            for variant in active_variants:
                current = variant.price
                regular = (
                    variant.compare_at_price
                    if variant.compare_at_price and variant.compare_at_price > current
                    else current
                )
                yield {
                    **base,
                    "id": variant.sku or f"variant-{variant.pk}",
                    "item_group_id": group_id,
                    "title": _clean(f"{product.name} — {variant.name}", 150),
                    "availability": (
                        "in_stock" if variant.available_to_sell else "out_of_stock"
                    ),
                    "price": f"{regular:.2f} {currency}",
                    "sale_price": (
                        f"{current:.2f} {currency}" if regular > current else ""
                    ),
                }
        else:
            current = product.price
            regular = (
                product.compare_at_price
                if product.compare_at_price and product.compare_at_price > current
                else current
            )
            yield {
                **base,
                "id": product.sku or f"product-{product.pk}",
                "item_group_id": "",
                "title": _clean(product.name, 150),
                "availability": (
                    "in_stock" if product.available_to_sell else "out_of_stock"
                ),
                "price": f"{regular:.2f} {currency}",
                "sale_price": (
                    f"{current:.2f} {currency}" if regular > current else ""
                ),
            }


FEED_FIELDS = [
    "id",
    "item_group_id",
    "title",
    "description",
    "link",
    "image_link",
    "additional_image_link",
    "availability",
    "condition",
    "price",
    "sale_price",
    "brand",
    "gtin",
    "mpn",
    "identifier_exists",
    "google_product_category",
    "product_type",
    "custom_label_0",
    "shipping_label",
]


def product_feed_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="leosoft-merchant-products.csv"'
    )
    writer = csv.DictWriter(response, fieldnames=FEED_FIELDS)
    writer.writeheader()
    for row in merchant_rows(request):
        out = dict(row)
        out["additional_image_link"] = ",".join(row["additional_image_link"])
        writer.writerow(out)
    return response


def product_feed_json(request):
    config = GrowthSettings.load()
    return JsonResponse(
        {
            "store": "LEOSOFT UG LTD",
            "country": config.merchant_country,
            "language": config.merchant_language,
            "products": list(merchant_rows(request)),
        }
    )


def product_feed_xml(request):
    config = GrowthSettings.load()
    company = CompanySettings.load()
    ET.register_namespace("g", GOOGLE_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "LEOSOFT UG LTD Merchant Center feed"
    ET.SubElement(channel, "link").text = request.build_absolute_uri("/")
    ET.SubElement(channel, "description").text = (
        "Published physical products from LEOSOFT UG LTD"
    )
    ns = f"{{{GOOGLE_NS}}}"

    for row in merchant_rows(request):
        item = ET.SubElement(channel, "item")
        for key in FEED_FIELDS:
            value = row.get(key)
            if not value:
                continue
            if key == "additional_image_link":
                for image_url in value:
                    ET.SubElement(item, f"{ns}{key}").text = image_url
                continue
            ET.SubElement(item, f"{ns}{key}").text = str(value)

        shipping = ET.SubElement(item, f"{ns}shipping")
        ET.SubElement(shipping, f"{ns}country").text = config.merchant_country
        ET.SubElement(shipping, f"{ns}service").text = (
            config.merchant_shipping_service
        )
        ET.SubElement(shipping, f"{ns}price").text = (
            f"{config.merchant_shipping_price:.2f} {company.currency_code}"
        )

    return HttpResponse(
        ET.tostring(rss, encoding="utf-8", xml_declaration=True),
        content_type="application/xml",
    )
