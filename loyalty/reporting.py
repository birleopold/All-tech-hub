from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from commerce.models import Order
from crm.models import Customer
from loyalty.models import (
    CustomerMarketingPreference,
    LoyaltyAccount,
    LoyaltyTransaction,
    MarketingConsentEvent,
)


VALID_CHANNELS = {"email", "whatsapp"}
VALID_SEGMENTS = {"all", "repeat", "dormant", "recent"}
VALID_TOPICS = {"product_updates", "special_offers"}


def customer_growth_summary(
    *,
    channel: str = "email",
    segment: str = "all",
    topic: str = "product_updates",
) -> dict:
    channel = channel if channel in VALID_CHANNELS else "email"
    segment = segment if segment in VALID_SEGMENTS else "all"
    topic = topic if topic in VALID_TOPICS else "product_updates"
    now = timezone.now()
    recent_cutoff = now - timedelta(days=90)

    preferences = CustomerMarketingPreference.objects.select_related("customer")
    email_count = preferences.filter(email_marketing=True).count()
    whatsapp_count = preferences.filter(whatsapp_marketing=True).count()
    both_count = preferences.filter(email_marketing=True, whatsapp_marketing=True).count()
    withdrawn_count = preferences.filter(
        email_marketing=False,
        whatsapp_marketing=False,
        withdrawn_at__isnull=False,
    ).count()

    channel_field = {
        "email": "marketing_preference__email_marketing",
        "whatsapp": "marketing_preference__whatsapp_marketing",
    }[channel]
    topic_field = f"marketing_preference__{topic}"
    eligible = Customer.objects.filter(
        **{
            channel_field: True,
            topic_field: True,
        }
    ).annotate(
        order_count=Count(
            "orders",
            filter=~Q(orders__status=Order.STATUS_CANCELLED),
            distinct=True,
        ),
        lifetime_value=Sum(
            "orders__total",
            filter=~Q(orders__status=Order.STATUS_CANCELLED),
        ),
        last_order_at=Max(
            "orders__placed_at",
            filter=~Q(orders__status=Order.STATUS_CANCELLED),
        ),
    ).select_related("marketing_preference", "loyalty_account")

    if segment == "repeat":
        eligible = eligible.filter(order_count__gte=2)
    elif segment == "dormant":
        eligible = eligible.filter(last_order_at__lt=recent_cutoff)
    elif segment == "recent":
        eligible = eligible.filter(last_order_at__gte=recent_cutoff)

    audience = list(
        eligible.order_by("-lifetime_value", "-last_order_at", "name", "id")[:100]
    )
    accounts = LoyaltyAccount.objects.all()
    tier_counts = {
        row["tier"]: row["count"]
        for row in accounts.values("tier").annotate(count=Count("id"))
    }
    points = accounts.aggregate(
        balance=Sum("points_balance"),
        lifetime=Sum("lifetime_points"),
    )

    return {
        "channel": channel,
        "segment": segment,
        "topic": topic,
        "total_customers": Customer.objects.count(),
        "preference_records": preferences.count(),
        "consent_event_count": MarketingConsentEvent.objects.count(),
        "email_consent_count": email_count,
        "whatsapp_consent_count": whatsapp_count,
        "both_consent_count": both_count,
        "withdrawn_count": withdrawn_count,
        "audience_count": eligible.count(),
        "audience": audience,
        "tier_counts": tier_counts,
        "loyalty_accounts": accounts.count(),
        "points_balance_total": points["balance"] or 0,
        "lifetime_points_total": points["lifetime"] or 0,
        "recent_cutoff": recent_cutoff,
    }


def consent_integrity_findings() -> dict:
    active_filter = Q(email_marketing=True) | Q(whatsapp_marketing=True)
    consent_without_date = CustomerMarketingPreference.objects.filter(
        active_filter,
        consented_at__isnull=True,
    ).count()
    active_without_event = CustomerMarketingPreference.objects.filter(active_filter).exclude(
        events__action__in=[
            MarketingConsentEvent.ACTION_GRANTED,
            MarketingConsentEvent.ACTION_UPDATED,
        ]
    ).count()
    topic_without_channel = CustomerMarketingPreference.objects.filter(
        email_marketing=False,
        whatsapp_marketing=False,
    ).filter(Q(product_updates=True) | Q(special_offers=True)).count()
    withdrawn_but_active = CustomerMarketingPreference.objects.filter(
        withdrawn_at__isnull=False,
    ).filter(active_filter).count()
    whatsapp_without_phone = CustomerMarketingPreference.objects.filter(
        whatsapp_marketing=True,
    ).filter(Q(customer__phone="") | Q(customer__phone__isnull=True)).count()

    account_mismatches = []
    for account in LoyaltyAccount.objects.select_related("customer"):
        transaction_total = (
            LoyaltyTransaction.objects.filter(account=account).aggregate(total=Sum("points_delta"))[
                "total"
            ]
            or 0
        )
        if transaction_total != account.points_balance:
            account_mismatches.append(
                {
                    "account_id": account.pk,
                    "customer": account.customer.name,
                    "balance": account.points_balance,
                    "transaction_total": transaction_total,
                }
            )

    awarded_references = LoyaltyTransaction.objects.filter(
        kind=LoyaltyTransaction.KIND_EARN,
        order_reference__gt="",
    ).values_list("order_reference", flat=True)
    awarded_orders_with_returns = list(
        Order.objects.filter(
            reference__in=awarded_references,
            lines__returns__isnull=False,
        )
        .distinct()
        .order_by("reference")
        .values_list("reference", flat=True)[:50]
    )
    awarded_orders_with_returns_count = (
        Order.objects.filter(
            reference__in=awarded_references,
            lines__returns__isnull=False,
        )
        .distinct()
        .count()
    )

    errors = (
        consent_without_date
        + active_without_event
        + topic_without_channel
        + withdrawn_but_active
        + whatsapp_without_phone
        + len(account_mismatches)
        + awarded_orders_with_returns_count
    )
    return {
        "errors": errors,
        "consent_without_date": consent_without_date,
        "active_without_event": active_without_event,
        "topic_without_channel": topic_without_channel,
        "withdrawn_but_active": withdrawn_but_active,
        "whatsapp_without_phone": whatsapp_without_phone,
        "loyalty_balance_mismatches": account_mismatches[:50],
        "loyalty_balance_mismatch_count": len(account_mismatches),
        "awarded_orders_with_returns": awarded_orders_with_returns,
        "awarded_orders_with_returns_count": awarded_orders_with_returns_count,
    }
