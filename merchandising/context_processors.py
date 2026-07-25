from django.db import OperationalError, ProgrammingError

from merchandising.models import BuyingGuide, CommercialLandingPage, DeliveryZone


def merchandising_context(request):
    """Small, failure-safe public discovery collections for navigation and home."""

    try:
        pages = list(
            CommercialLandingPage.objects.filter(is_published=True)
            .only("title", "slug", "eyebrow", "meta_description", "sort_order")
            .order_by("sort_order", "title")[:12]
        )
        guides = list(
            BuyingGuide.objects.filter(is_published=True)
            .only("title", "slug", "excerpt", "author_name", "reviewer_name", "published_at", "updated_at")
            .order_by("-published_at", "-id")[:6]
        )
        zones = list(
            DeliveryZone.objects.filter(is_active=True)
            .only("name", "areas", "fee_from", "lead_time", "notes", "sort_order")
            .order_by("sort_order", "name")[:6]
        )
    except (OperationalError, ProgrammingError):
        pages, guides, zones = [], [], []
    return {
        "commercial_landing_pages": pages,
        "latest_buying_guides": guides,
        "public_delivery_zones": zones,
    }
