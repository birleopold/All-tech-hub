from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from commerce.models import Order
from crm.models import Customer
from loyalty.models import (
    CustomerMarketingPreference,
    LoyaltyAccount,
    LoyaltyTransaction,
    MarketingConsentEvent,
)


CONSENT_TEXT_VERSION = "2026-07"
COMPLETED_STATUSES = {Order.STATUS_DELIVERED, Order.STATUS_FULFILLED}


def ensure_marketing_preference(customer: Customer) -> CustomerMarketingPreference:
    preference, _ = CustomerMarketingPreference.objects.get_or_create(customer=customer)
    return preference


def _consent_state(preference: CustomerMarketingPreference) -> tuple[bool, bool, bool, bool]:
    return (
        preference.email_marketing,
        preference.whatsapp_marketing,
        preference.product_updates,
        preference.special_offers,
    )


def _record_consent_event(
    preference: CustomerMarketingPreference,
    *,
    previous_state: tuple[bool, bool, bool, bool],
) -> MarketingConsentEvent | None:
    current_state = _consent_state(preference)
    if current_state == previous_state:
        return None
    previous_any = previous_state[0] or previous_state[1]
    current_any = current_state[0] or current_state[1]
    if current_any and not previous_any:
        action = MarketingConsentEvent.ACTION_GRANTED
    elif previous_any and not current_any:
        action = MarketingConsentEvent.ACTION_WITHDRAWN
    else:
        action = MarketingConsentEvent.ACTION_UPDATED
    return MarketingConsentEvent.objects.create(
        preference=preference,
        customer=preference.customer,
        action=action,
        source=preference.consent_source,
        email_marketing=preference.email_marketing,
        whatsapp_marketing=preference.whatsapp_marketing,
        product_updates=preference.product_updates,
        special_offers=preference.special_offers,
        consent_text_version=preference.consent_text_version,
    )


@transaction.atomic
def update_marketing_preference(
    customer: Customer,
    *,
    email_marketing: bool,
    whatsapp_marketing: bool,
    product_updates: bool,
    special_offers: bool,
    source: str,
) -> CustomerMarketingPreference:
    preference = ensure_marketing_preference(customer)
    preference = CustomerMarketingPreference.objects.select_for_update().get(
        pk=preference.pk
    )
    previous_state = _consent_state(preference)
    preference.email_marketing = bool(email_marketing)
    preference.whatsapp_marketing = bool(whatsapp_marketing)
    preference.product_updates = bool(product_updates) and preference.has_any_consent
    preference.special_offers = bool(special_offers) and preference.has_any_consent
    preference.consent_source = source
    preference.consent_text_version = CONSENT_TEXT_VERSION
    preference.save()
    _record_consent_event(preference, previous_state=previous_state)
    return preference


@transaction.atomic
def add_checkout_consent(
    customer: Customer,
    *,
    email_marketing: bool = False,
    whatsapp_marketing: bool = False,
) -> CustomerMarketingPreference | None:
    if not email_marketing and not whatsapp_marketing:
        return None
    preference = ensure_marketing_preference(customer)
    preference = CustomerMarketingPreference.objects.select_for_update().get(
        pk=preference.pk
    )
    previous_state = _consent_state(preference)
    preference.email_marketing = preference.email_marketing or bool(email_marketing)
    preference.whatsapp_marketing = preference.whatsapp_marketing or bool(whatsapp_marketing)
    preference.product_updates = True
    preference.special_offers = True
    preference.consent_source = CustomerMarketingPreference.SOURCE_CHECKOUT
    preference.consent_text_version = CONSENT_TEXT_VERSION
    preference.save()
    _record_consent_event(preference, previous_state=previous_state)
    return preference


@transaction.atomic
def withdraw_all_marketing(preference: CustomerMarketingPreference) -> CustomerMarketingPreference:
    preference = CustomerMarketingPreference.objects.select_for_update().get(
        pk=preference.pk
    )
    previous_state = _consent_state(preference)
    preference.email_marketing = False
    preference.whatsapp_marketing = False
    preference.product_updates = False
    preference.special_offers = False
    preference.withdrawn_at = timezone.now()
    preference.save()
    _record_consent_event(preference, previous_state=previous_state)
    return preference


def consented_customers(*, channel: str, topic: str):
    channel_field = {
        "email": "marketing_preference__email_marketing",
        "whatsapp": "marketing_preference__whatsapp_marketing",
    }.get(channel)
    topic_field = {
        "product_updates": "marketing_preference__product_updates",
        "special_offers": "marketing_preference__special_offers",
    }.get(topic)
    if channel_field is None or topic_field is None:
        return Customer.objects.none()
    return Customer.objects.filter(
        **{
            channel_field: True,
            topic_field: True,
        }
    ).order_by("name", "id")


def _tier_for_lifetime_points(points: int) -> str:
    thresholds = [
        (int(getattr(settings, "LOYALTY_PLATINUM_POINTS", 1500)), LoyaltyAccount.TIER_PLATINUM),
        (int(getattr(settings, "LOYALTY_GOLD_POINTS", 500)), LoyaltyAccount.TIER_GOLD),
        (int(getattr(settings, "LOYALTY_SILVER_POINTS", 100)), LoyaltyAccount.TIER_SILVER),
    ]
    for threshold, tier in thresholds:
        if points >= max(0, threshold):
            return tier
    return LoyaltyAccount.TIER_MEMBER


def points_for_order(order: Order) -> int:
    spend_per_point = max(
        Decimal("1"),
        Decimal(str(getattr(settings, "LOYALTY_SPEND_PER_POINT", 10000))),
    )
    return max(
        0,
        int((Decimal(order.total) / spend_per_point).to_integral_value(rounding=ROUND_FLOOR)),
    )


@transaction.atomic
def award_completed_order_points(order: Order) -> LoyaltyTransaction | None:
    if not bool(getattr(settings, "LOYALTY_POINTS_ENABLED", False)):
        return None
    order = Order.objects.select_related("customer").get(pk=order.pk)
    if order.status not in COMPLETED_STATUSES:
        return None
    points = points_for_order(order)
    if points <= 0:
        return None

    key = f"order:{order.pk}:completed"
    account, _ = LoyaltyAccount.objects.get_or_create(customer=order.customer)
    account = LoyaltyAccount.objects.select_for_update().get(pk=account.pk)
    existing = LoyaltyTransaction.objects.filter(idempotency_key=key).first()
    if existing:
        return existing

    transaction_row = LoyaltyTransaction.objects.create(
        account=account,
        kind=LoyaltyTransaction.KIND_EARN,
        points_delta=points,
        idempotency_key=key,
        order_reference=order.reference,
        note=f"Points earned from completed order {order.reference}",
    )
    account.points_balance += points
    account.lifetime_points += points
    account.tier = _tier_for_lifetime_points(account.lifetime_points)
    account.save(
        update_fields=["points_balance", "lifetime_points", "tier", "updated_at"]
    )
    return transaction_row


def award_completed_order_points_by_id(order_id: int):
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return None
    return award_completed_order_points(order)


def ensure_loyalty_account(customer: Customer) -> LoyaltyAccount:
    account, _ = LoyaltyAccount.objects.get_or_create(customer=customer)
    expected_tier = _tier_for_lifetime_points(account.lifetime_points)
    if account.tier != expected_tier:
        account.tier = expected_tier
        account.save(update_fields=["tier", "updated_at"])
    return account
