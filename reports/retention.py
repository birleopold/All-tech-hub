from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Max, Sum
from django.utils import timezone

from catalog.models import ProductReview, ProductSerial
from commerce.customer_messages import customer_email_delivery_ready
from commerce.models import Order
from commerce.retention import REVIEW_SUBJECT_PREFIX
from messaging.models import OutboundEmail


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def retention_summary(days: int = 90) -> dict:
    days = max(1, min(int(days), 365))
    now = timezone.now()
    since = now - timedelta(days=days)
    all_orders = Order.objects.exclude(status=Order.STATUS_CANCELLED)
    period_orders = all_orders.filter(placed_at__gte=since)

    lifetime = {
        row["customer_id"]: row
        for row in all_orders.values("customer_id")
        .annotate(
            order_count=Count("id"),
            lifetime_value=Sum("total"),
            last_order_at=Max("placed_at"),
        )
    }
    period_rows = list(
        period_orders.select_related("customer").order_by("placed_at", "id")
    )
    period_customer_ids = {order.customer_id for order in period_rows}
    repeat_customer_ids = {
        customer_id
        for customer_id in period_customer_ids
        if lifetime.get(customer_id, {}).get("order_count", 0) >= 2
    }
    repeat_orders = [
        order for order in period_rows if order.customer_id in repeat_customer_ids
    ]
    repeat_revenue = sum((order.total for order in repeat_orders), Decimal("0.00"))
    revenue = sum((order.total for order in period_rows), Decimal("0.00"))

    first_order_at: dict[int, object] = {}
    for customer_id, placed_at in all_orders.order_by("placed_at", "id").values_list(
        "customer_id", "placed_at"
    ):
        first_order_at.setdefault(customer_id, placed_at)
    returning_orders = sum(
        1
        for order in period_rows
        if first_order_at.get(order.customer_id) and first_order_at[order.customer_id] < order.placed_at
    )

    completed_orders = period_orders.filter(
        status__in=[Order.STATUS_DELIVERED, Order.STATUS_FULFILLED]
    )
    completed_count = completed_orders.count()
    review_requests = OutboundEmail.objects.filter(
        created_at__gte=since,
        subject__startswith=REVIEW_SUBJECT_PREFIX,
    )
    review_requests_sent = review_requests.filter(
        status=OutboundEmail.STATUS_SENT
    ).count()
    review_requests_failed = review_requests.filter(
        status=OutboundEmail.STATUS_FAILED
    ).count()
    verified_reviews = ProductReview.objects.filter(
        created_at__gte=since,
        is_verified_purchase=True,
    )
    verified_review_count = verified_reviews.count()
    published_verified_reviews = verified_reviews.filter(is_published=True).count()
    average_rating = (
        verified_reviews.aggregate(total=Sum("rating"))["total"] / verified_review_count
        if verified_review_count
        else None
    )

    warranty_start = timezone.localdate()
    warranty_end = warranty_start + timedelta(days=30)
    expiring_warranties = []
    for serial in ProductSerial.objects.filter(
        status=ProductSerial.STATUS_SOLD,
        sold_to__isnull=False,
        warranty_months__gt=0,
    ).select_related("product", "product_variant", "sold_to"):
        expires = serial.warranty_expires_on
        if expires and warranty_start <= expires <= warranty_end:
            expiring_warranties.append(serial)
    expiring_warranties.sort(key=lambda serial: serial.warranty_expires_on)

    dormant_cutoff = now - timedelta(days=90)
    dormant_customers = []
    for customer_id, row in lifetime.items():
        if row["last_order_at"] >= dormant_cutoff:
            continue
        customer_order = (
            all_orders.filter(customer_id=customer_id)
            .select_related("customer")
            .order_by("-placed_at", "-id")
            .first()
        )
        if customer_order:
            dormant_customers.append(
                {
                    "customer": customer_order.customer,
                    "last_order_at": row["last_order_at"],
                    "order_count": row["order_count"],
                    "lifetime_value": row["lifetime_value"] or Decimal("0.00"),
                }
            )
    dormant_customers.sort(key=lambda row: row["lifetime_value"], reverse=True)

    top_customers = []
    for customer_id in period_customer_ids:
        latest = (
            period_orders.filter(customer_id=customer_id)
            .select_related("customer")
            .order_by("-placed_at", "-id")
            .first()
        )
        if latest:
            row = lifetime[customer_id]
            top_customers.append(
                {
                    "customer": latest.customer,
                    "order_count": row["order_count"],
                    "lifetime_value": row["lifetime_value"] or Decimal("0.00"),
                    "last_order_at": row["last_order_at"],
                }
            )
    top_customers.sort(key=lambda row: row["lifetime_value"], reverse=True)

    return {
        "days": days,
        "since": since,
        "order_count": len(period_rows),
        "revenue": revenue,
        "unique_customers": len(period_customer_ids),
        "repeat_customers": len(repeat_customer_ids),
        "repeat_customer_rate": _rate(len(repeat_customer_ids), len(period_customer_ids)),
        "returning_orders": returning_orders,
        "returning_order_rate": _rate(returning_orders, len(period_rows)),
        "repeat_revenue": repeat_revenue,
        "repeat_revenue_rate": (
            (repeat_revenue / revenue * Decimal("100")).quantize(Decimal("0.01"))
            if revenue > 0
            else Decimal("0.00")
        ),
        "completed_orders": completed_count,
        "review_requests_sent": review_requests_sent,
        "review_requests_failed": review_requests_failed,
        "review_request_coverage": _rate(review_requests_sent, completed_count),
        "verified_review_count": verified_review_count,
        "published_verified_reviews": published_verified_reviews,
        "average_verified_rating": round(float(average_rating), 1)
        if average_rating is not None
        else None,
        "review_email_enabled": bool(
            getattr(settings, "ORDER_REVIEW_EMAILS_ENABLED", False)
        ),
        "email_delivery_ready": customer_email_delivery_ready(),
        "expiring_warranty_count": len(expiring_warranties),
        "expiring_warranties": expiring_warranties[:20],
        "dormant_customer_count": len(dormant_customers),
        "dormant_customers": dormant_customers[:15],
        "top_customers": top_customers[:15],
    }
