from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, F, Sum
from django.utils import timezone

from commerce.customer_messages import customer_email_delivery_ready
from commerce.models import Order
from growth.models import SavedCart
from marketing.attribution_metrics import merge_channel_metrics, percentage
from marketing.models import CampaignClick, MarketingCampaign, MarketingLead
from messaging.models import OutboundEmail


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def marketing_attribution_summary(days: int = 30) -> dict:
    """Period-matched clicks, leads and placed-order values, not cash receipts."""
    days = max(1, min(int(days), 365))
    since = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(placed_at__gte=since).exclude(
        status=Order.STATUS_CANCELLED
    )
    attributed_orders = orders.exclude(marketing_source="")
    click_rows = CampaignClick.objects.filter(occurred_at__gte=since).values(
        source=F("link__source"), medium=F("link__medium")
    ).annotate(clicks=Count("id"))
    lead_rows = MarketingLead.objects.filter(created_at__gte=since).values(
        "source", "medium"
    ).annotate(leads=Count("id"))
    order_rows = attributed_orders.values(
        source=F("marketing_source"), medium=F("marketing_medium")
    ).annotate(orders=Count("id"), revenue=Sum("total"))
    channels = merge_channel_metrics(click_rows, lead_rows, order_rows)

    campaign_rows = list(
        attributed_orders.exclude(marketing_campaign="").values(
            "marketing_campaign"
        ).annotate(orders=Count("id"), revenue=Sum("total"))
    )
    campaigns_by_slug = {
        campaign.slug: campaign
        for campaign in MarketingCampaign.objects.filter(
            slug__in=[row["marketing_campaign"] for row in campaign_rows]
        )
    }
    for row in campaign_rows:
        campaign = campaigns_by_slug.get(row["marketing_campaign"])
        budget = campaign.budget if campaign else Decimal("0.00")
        row["name"] = campaign.name if campaign else row["marketing_campaign"]
        row["budget"] = budget
        row["budget_return"] = (
            (Decimal(str(row["revenue"])) / budget).quantize(Decimal("0.01"))
            if budget > 0
            else None
        )
    campaign_rows.sort(key=lambda row: -row["revenue"])

    attributed = attributed_orders.aggregate(count=Count("id"), revenue=Sum("total"))
    attributed_count = attributed["count"] or 0
    total_orders = orders.count()
    return {
        "days": days,
        "channels": channels,
        "campaigns": campaign_rows,
        "attributed_orders": attributed_count,
        "attributed_revenue": attributed["revenue"] or Decimal("0.00"),
        "attributed_order_value": attributed["revenue"] or Decimal("0.00"),
        "unattributed_orders": total_orders - attributed_count,
        "attribution_rate": percentage(attributed_count, total_orders),
    }


def conversion_summary(days: int = 30) -> dict:
    days = max(1, min(int(days), 365))
    since = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(placed_at__gte=since)
    non_cancelled = orders.exclude(status=Order.STATUS_CANCELLED)
    order_agg = non_cancelled.aggregate(
        count=Count("id"),
        revenue=Sum("total"),
        average=Avg("total"),
    )
    order_count = order_agg["count"] or 0
    revenue = order_agg["revenue"] or Decimal("0")
    average = order_agg["average"] or Decimal("0")

    saved = SavedCart.objects.filter(created_at__gte=since)
    saved_count = saved.count()
    saved_recovered = saved.filter(status=SavedCart.STATUS_RECOVERED).count()
    saved_active = saved.filter(status=SavedCart.STATUS_ACTIVE).count()
    saved_expired = saved.filter(status=SavedCart.STATUS_EXPIRED).count()
    saved_unsubscribed = saved.filter(status=SavedCart.STATUS_UNSUBSCRIBED).count()
    recovered_revenue = (
        saved.filter(
            status=SavedCart.STATUS_RECOVERED,
            recovered_order__isnull=False,
        ).aggregate(total=Sum("recovered_order__total"))["total"]
        or Decimal("0")
    )

    sent_subjects = list(
        OutboundEmail.objects.filter(
            status=OutboundEmail.STATUS_SENT,
            created_at__gte=since,
            subject__startswith="Order ",
        ).values_list("subject", flat=True)
    )
    sent_subject_set = set(sent_subjects)
    missing_confirmation = 0
    for reference in non_cancelled.values_list("reference", flat=True):
        if not any(
            subject.startswith(f"Order {reference} received")
            for subject in sent_subject_set
        ):
            missing_confirmation += 1

    failed_order_emails = OutboundEmail.objects.filter(
        status=OutboundEmail.STATUS_FAILED,
        created_at__gte=since,
        subject__startswith="Order ",
    ).count()
    status_emails_sent = sum(1 for subject in sent_subjects if ":" in subject)
    pending_older_than_24h = orders.filter(
        status=Order.STATUS_PENDING,
        placed_at__lt=timezone.now() - timedelta(hours=24),
    ).count()
    coupon_orders = non_cancelled.exclude(coupon_code_applied="").count()
    recovered_denominator = saved_recovered + saved_active + saved_expired + saved_unsubscribed
    non_recovered_saved = saved_active + saved_expired + saved_unsubscribed
    conversion_denominator = order_count + non_recovered_saved

    attribution = marketing_attribution_summary(days)
    return {
        "days": days,
        "since": since,
        "order_count": order_count,
        "cancelled_orders": orders.filter(status=Order.STATUS_CANCELLED).count(),
        "revenue": revenue,
        "average_order_value": average,
        "coupon_orders": coupon_orders,
        "coupon_order_rate": _rate(coupon_orders, order_count),
        "saved_cart_count": saved_count,
        "saved_cart_recovered": saved_recovered,
        "saved_cart_active": saved_active,
        "saved_cart_expired": saved_expired,
        "saved_cart_unsubscribed": saved_unsubscribed,
        "saved_cart_recovery_rate": _rate(saved_recovered, recovered_denominator),
        "recovered_revenue": recovered_revenue,
        "checkout_conversion_proxy": _rate(order_count, conversion_denominator),
        "order_emails_enabled": bool(
            getattr(settings, "ORDER_CUSTOMER_EMAILS_ENABLED", True)
        ),
        "email_delivery_ready": customer_email_delivery_ready(),
        "missing_confirmation_emails": missing_confirmation,
        "failed_order_emails": failed_order_emails,
        "status_emails_sent": status_emails_sent,
        "pending_older_than_24h": pending_older_than_24h,
        "attribution": attribution,
        "status_counts": [
            {
                "value": value,
                "label": label,
                "count": orders.filter(status=value).count(),
            }
            for value, label in Order.STATUS_CHOICES
        ],
    }
