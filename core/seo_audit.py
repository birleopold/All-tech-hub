from __future__ import annotations

from django.conf import settings
from django.db.models import Count, Q
from django.urls import reverse

from catalog.models import Category, Product
from core.models import CompanySettings
from core.seo import public_base_url, public_url
from growth.models import GrowthSettings


def seo_audit_snapshot() -> dict:
    company = CompanySettings.load()
    growth = GrowthSettings.load()
    published = Product.objects.filter(is_published=True)
    physical = published.filter(kind=Product.KIND_PHYSICAL)

    products_without_images = (
        physical.filter(Q(image__isnull=True) | Q(image=""))
        .exclude(gallery_images__image__isnull=False)
        .distinct()
        .count()
    )
    products_without_description = published.filter(
        Q(short_description="") & Q(description="")
    ).count()
    physical_without_sku = physical.filter(sku="").count()
    physical_without_growth = physical.filter(growth_data__isnull=True).count()
    physical_without_brand = physical.filter(
        Q(growth_data__isnull=True) | Q(growth_data__brand="")
    ).count()
    physical_without_identifiers = physical.filter(
        Q(growth_data__isnull=True)
        | (
            Q(growth_data__gtin="")
            & (Q(growth_data__mpn="") | Q(growth_data__brand=""))
        )
    ).count()
    category_rows = Category.objects.annotate(
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
    ).filter(Q(direct_count__gt=0) | Q(child_count__gt=0))
    categories_without_description = category_rows.filter(description="").count()

    critical = []
    warnings = []
    successes = []

    if not public_base_url().startswith("https://"):
        critical.append("The canonical public URL is not using HTTPS.")
    else:
        successes.append("Canonical public origin uses HTTPS.")
    if not company.company_name.strip():
        critical.append("Company name is missing.")
    if not published.exists():
        critical.append("No public products or services are published.")
    if products_without_images:
        warnings.append(
            f"{products_without_images} published physical products have no discoverable image."
        )
    if products_without_description:
        warnings.append(
            f"{products_without_description} published listings have no unique description."
        )
    if physical_without_sku:
        warnings.append(f"{physical_without_sku} physical products have no internal SKU.")
    if physical_without_growth:
        warnings.append(
            f"{physical_without_growth} physical products have no feed metadata record."
        )
    if physical_without_brand:
        warnings.append(f"{physical_without_brand} physical products have no brand metadata.")
    if physical_without_identifiers:
        warnings.append(
            f"{physical_without_identifiers} physical products have no GTIN or brand-and-MPN manufacturer identifier."
        )
    if categories_without_description:
        warnings.append(
            f"{categories_without_description} public categories need useful unique descriptions."
        )

    if not company.logo:
        warnings.append("Company logo is missing from organization and social metadata.")
    if not company.phone and not company.email:
        warnings.append("No public phone or email is configured for trust and local SEO.")
    if not company.address_line and not company.city:
        warnings.append("Business address and city are missing from local organization data.")
    if not company.website:
        warnings.append("Company website field is empty; use the canonical production URL.")
    if not growth.search_console_verification_token:
        warnings.append("Google Search Console verification token is not configured.")
    else:
        successes.append("Google Search Console verification is configured.")
    if not getattr(settings, "BING_SITE_VERIFICATION_TOKEN", ""):
        warnings.append("Bing Webmaster Tools verification token is not configured.")
    else:
        successes.append("Bing Webmaster Tools verification is configured.")
    if not growth.google_business_profile_url:
        warnings.append("Google Business Profile URL is not linked.")
    else:
        successes.append("Google Business Profile is linked.")
    if not growth.merchant_return_policy_url:
        warnings.append("Merchant return-policy URL is missing.")
    else:
        successes.append("Merchant return-policy URL is configured for customer use.")
    if not getattr(settings, "INDEXNOW_KEY", ""):
        warnings.append("IndexNow key is not configured.")
    elif not getattr(settings, "INDEXNOW_ENABLED", False):
        warnings.append("IndexNow has a key but live submission is disabled.")
    else:
        successes.append("IndexNow submission is enabled.")
    if not getattr(settings, "SEO_DEFAULT_IMAGE_URL", "") and not company.logo:
        warnings.append("No default social sharing image is configured.")

    endpoints = {
        "canonical_origin": public_base_url(),
        "sitemap_index": public_url(reverse("sitemap_index")),
        "image_sitemap": public_url(reverse("image_sitemap")),
        "merchant_feed": public_url(reverse("google_merchant_feed")),
        "robots": public_url(reverse("robots_txt")),
        "indexnow_key": public_url(reverse("indexnow_key")),
    }
    endpoint_rows = [
        {"label": "Canonical origin", "url": endpoints["canonical_origin"]},
        {"label": "Sitemap index", "url": endpoints["sitemap_index"]},
        {"label": "Image sitemap", "url": endpoints["image_sitemap"]},
        {"label": "Google Merchant feed", "url": endpoints["merchant_feed"]},
        {"label": "Robots file", "url": endpoints["robots"]},
        {"label": "IndexNow ownership key", "url": endpoints["indexnow_key"]},
    ]
    metrics = {
        "published_listings": published.count(),
        "published_physical_products": physical.count(),
        "public_categories": category_rows.count(),
        "products_without_images": products_without_images,
        "products_without_description": products_without_description,
        "physical_without_sku": physical_without_sku,
        "physical_without_brand": physical_without_brand,
        "physical_without_identifiers": physical_without_identifiers,
        "categories_without_description": categories_without_description,
    }
    score = max(0, 100 - len(critical) * 20 - len(warnings) * 4)
    return {
        "score": score,
        "critical": critical,
        "warnings": warnings,
        "successes": successes,
        "metrics": metrics,
        "endpoints": endpoints,
        "endpoint_rows": endpoint_rows,
    }
