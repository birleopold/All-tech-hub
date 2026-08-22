"""First-party, last-click marketing attribution for completed checkouts."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from marketing.models import CampaignLink

SESSION_ATTRIBUTION_KEY = "marketing_attribution"


def order_attribution(session, *, now=None) -> dict:
    """Return verified order fields for a recent tracked-link session, if any."""
    raw = session.get(SESSION_ATTRIBUTION_KEY)
    if not isinstance(raw, dict):
        return {}

    try:
        link_id = int(raw.get("link_id"))
        clicked_at = datetime.fromisoformat(str(raw.get("clicked_at", "")))
    except (TypeError, ValueError, OverflowError):
        return {}

    if link_id <= 0 or timezone.is_naive(clicked_at):
        return {}
    now = now or timezone.now()
    max_days = max(
        1,
        min(365, int(getattr(settings, "MARKETING_ATTRIBUTION_WINDOW_DAYS", 30))),
    )
    if clicked_at < now - timedelta(days=max_days):
        return {}
    if clicked_at > now + timedelta(minutes=5):
        return {}

    link = CampaignLink.objects.select_related("campaign", "product").filter(
        pk=link_id
    ).first()
    if link is None:
        return {}
    return {
        "marketing_link": link,
        "marketing_source": link.source[:60],
        "marketing_medium": link.medium[:60],
        "marketing_campaign": (
            link.campaign.slug[:200] if link.campaign else "leosoft"
        ),
        "marketing_content": (
            link.content or (link.product.slug if link.product else link.code)
        )[:120],
        "marketing_attributed_at": clicked_at,
    }
