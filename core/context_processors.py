from django.db.models import Count, Q

from catalog.models import Category
from core.models import CompanySettings, StaffNotification, is_open_now


PUBLIC_QUICK_COLLECTIONS = [
    {"slug": "deals", "label": "Deals", "icon": "bi-tags"},
    {"slug": "new", "label": "New arrivals", "icon": "bi-lightning-charge"},
    {"slug": "refurbished", "label": "Refurbished", "icon": "bi-arrow-repeat"},
    {"slug": "business", "label": "Business", "icon": "bi-briefcase"},
    {"slug": "student", "label": "Students", "icon": "bi-mortarboard"},
]


def company(request):
    m = getattr(request, "resolver_match", None)
    url_name = getattr(m, "url_name", "") or ""
    company_settings = CompanySettings.load()
    ctx = {
        "company": company_settings,
        "resolve_url_name": url_name,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        ctx["staff_unread_notifications"] = StaffNotification.objects.filter(
            recipient=user, is_read=False
        ).count()
    else:
        ctx["staff_unread_notifications"] = 0

    path = getattr(request, "path", "") or ""
    public_navigation_enabled = not (
        path.startswith("/staff/")
        or path.startswith("/admin/")
        or url_name.startswith("staff_")
    )
    ctx["public_navigation_enabled"] = public_navigation_enabled
    ctx["public_quick_collections"] = PUBLIC_QUICK_COLLECTIONS

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
        ctx["public_nav_categories"] = categories
        ctx["site_is_open"] = is_open_now()
        location_parts = [
            company_settings.address_line,
            company_settings.city,
            company_settings.region,
        ]
        ctx["public_location_label"] = ", ".join(
            part.strip() for part in location_parts if part and part.strip()
        )
    else:
        ctx["public_nav_categories"] = []
        ctx["site_is_open"] = False
        ctx["public_location_label"] = ""

    return ctx
