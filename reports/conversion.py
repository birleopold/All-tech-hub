from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from commerce.customer_messages import customer_email_delivery_ready
from commerce.models import Order
from growth.models import SavedCart
from messaging.models import OutboundEmail


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(
        Decimal("0.01")
    )


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
        "status_counts": [
            {
                "value": value,
                "label": label,
                "count": orders.filter(status=value).count(),
            }
            for value, label in Order.STATUS_CHOICES
        ],
    }
