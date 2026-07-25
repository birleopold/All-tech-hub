import json

from django.conf import settings
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.safestring import mark_safe

from catalog.models import Category
from core.models import CompanySettings, StaffNotification, is_open_now
from core.seo import meta_description, meta_title, public_url


PUBLIC_QUICK_COLLECTIONS = [
    {"slug": "deals", "label": "Deals", "icon": "bi-tags"},
    {"slug": "new", "label": "New arrivals", "icon": "bi-lightning-charge"},
    {"slug": "refurbished", "label": "Refurbished", "icon": "bi-arrow-repeat"},
    {"slug": "business", "label": "Business", "icon": "bi-briefcase"},
    {"slug": "student", "label": "Students", "icon": "bi-mortarboard"},
]


def _script_safe_json(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return mark_safe(
        encoded
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def company(request):
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") or ""
    company_settings = CompanySettings.load()
    default_title = meta_title(
        getattr(settings, "SEO_DEFAULT_TITLE", ""),
        fallback=f"{company_settings.company_name} — Technology products and IT support",
    )
    default_description = meta_description(
        getattr(settings, "SEO_DEFAULT_DESCRIPTION", ""),
        fallback=(
            company_settings.tagline
            or "Computers, accessories, repairs, installations and business IT support."
        ),
    )
    configured_image = (getattr(settings, "SEO_DEFAULT_IMAGE_URL", "") or "").strip()
    if configured_image:
        default_image = public_url(configured_image)
    elif company_settings.logo:
        default_image = public_url(company_settings.logo.url)
    else:
        default_image = ""

    context = {
        "company": company_settings,
        "resolve_url_name": url_name,
        "seo_default_title": default_title,
        "seo_default_description": default_description,
        "seo_default_canonical_url": public_url(getattr(request, "path", "/") or "/"),
        "seo_default_image_url": default_image,
        "seo_twitter_site": (getattr(settings, "SEO_TWITTER_SITE", "") or "").strip(),
        "bing_site_verification_token": (
            getattr(settings, "BING_SITE_VERIFICATION_TOKEN", "") or ""
        ).strip(),
        "seo_image_sitemap_url": public_url("/image-sitemap.xml"),
        "seo_merchant_feed_url": public_url("/feeds/google-merchant.xml"),
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        context["staff_unread_notifications"] = StaffNotification.objects.filter(
            recipient=user,
            is_read=False,
        ).count()
    else:
        context["staff_unread_notifications"] = 0

    path = getattr(request, "path", "") or ""
    public_navigation_enabled = not (
        path.startswith("/staff/")
        or path.startswith("/admin/")
        or url_name.startswith("staff_")
    )
    context["public_navigation_enabled"] = public_navigation_enabled
    context["public_quick_collections"] = PUBLIC_QUICK_COLLECTIONS

    if public_navigation_enabled:
        categories = list(
            Category.objects.filter(parent__isnull=True)
            .annotate(
                direct_product_count=Count(
                    "products",
                    filter=Q(products__is_published=True),
                    distinct=True,
                ),
                child_product_count=Count(
                    "subcategories__products",
                    filter=Q(subcategories__products__is_published=True),
                    distinct=True,
                ),
            )
            .prefetch_related("subcategories")
            .order_by("sort_order", "name")[:10]
        )
        for category in categories:
            category.public_item_count = (
                category.direct_product_count + category.child_product_count
            )
            category.public_subcategories = list(category.subcategories.all()[:8])
        context["public_nav_categories"] = categories
        context["site_is_open"] = is_open_now()
        location_parts = [
            company_settings.address_line,
            company_settings.city,
            company_settings.region,
        ]
        context["public_location_label"] = ", ".join(
            part.strip() for part in location_parts if part and part.strip()
        )

        if url_name == "home":
            home_url = public_url(reverse("home"))
            catalogue_url = public_url(reverse("product_list"))
            context["website_schema_json"] = _script_safe_json(
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "@id": f"{home_url}#website",
                    "name": company_settings.company_name,
                    "url": home_url,
                    "inLanguage": "en-UG",
                    "potentialAction": {
                        "@type": "SearchAction",
                        "target": {
                            "@type": "EntryPoint",
                            "urlTemplate": f"{catalogue_url}?q={{search_term_string}}",
                        },
                        "query-input": "required name=search_term_string",
                    },
                }
            )
        else:
            context["website_schema_json"] = ""
    else:
        context["public_nav_categories"] = []
        context["site_is_open"] = False
        context["public_location_label"] = ""
        context["website_schema_json"] = ""

    return context
