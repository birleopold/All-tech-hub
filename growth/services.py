from decimal import Decimal
from urllib.parse import urljoin

from django.db.models import Count, Sum
from django.utils import timezone

from catalog.models import Product, ProductVariant
from commerce import cart as cart_mod
from core.models import CompanySettings
from growth.models import (
    Ambassador,
    AmbassadorConversion,
    AmbassadorLead,
    ContentAsset,
    GrowthSettings,
    SavedCart,
    StockAlertSubscription,
)
from messaging.models import OutboundEmail
from messaging.utils import send_outbound_email

ANALYTICS_SESSION_KEY = "growth_analytics_events"
PURCHASE_SESSION_KEY = "growth_purchase_order"
AMBASSADOR_SESSION_KEY = "growth_ambassador_code"


def company_base_url() -> str:
    company = CompanySettings.load()
    return (company.website or "https://leosoftug.com").rstrip("/") + "/"


def absolute_public_url(path: str) -> str:
    return urljoin(company_base_url(), path.lstrip("/"))


def _growth_data(product: Product):
    try:
        return product.growth_data
    except Exception:
        return None


def analytics_item(
    product: Product,
    *,
    variant: ProductVariant | None = None,
    quantity: int = 1,
    index: int | None = None,
) -> dict:
    price = variant.price if variant else (product.min_active_variant_price or product.price)
    item = {
        "item_id": (variant.sku if variant and variant.sku else product.sku)
        or str(variant.pk if variant else product.pk),
        "item_name": product.name,
        "item_category": product.category.name,
        "item_variant": variant.name if variant else "",
        "price": float(price),
        "quantity": int(quantity),
    }
    metadata = _growth_data(product)
    if metadata and metadata.brand:
        item["item_brand"] = metadata.brand
    if index is not None:
        item["index"] = int(index)
    return item


def analytics_event(name: str, params: dict) -> dict:
    return {"name": name, "params": params}


def queue_analytics_event(request, name: str, params: dict) -> None:
    events = request.session.get(ANALYTICS_SESSION_KEY, [])
    if not isinstance(events, list):
        events = []
    events.append(analytics_event(name, params))
    request.session[ANALYTICS_SESSION_KEY] = events[-10:]
    request.session.modified = True


def purchase_event(order) -> dict:
    company = CompanySettings.load()
    items = []
    for line in order.lines.select_related(
        "product",
        "product__category",
        "product_variant",
    ):
        if line.product:
            items.append(
                analytics_item(
                    line.product,
                    variant=line.product_variant,
                    quantity=line.quantity,
                )
            )
        else:
            items.append(
                {
                    "item_id": line.sku or str(line.pk),
                    "item_name": line.description,
                    "price": float(line.unit_price),
                    "quantity": line.quantity,
                }
            )
    return analytics_event(
        "purchase",
        {
            "transaction_id": order.reference,
            "value": float(order.total),
            "tax": float(order.tax_amount),
            "shipping": float(order.delivery_fee),
            "currency": company.currency_code,
            "coupon": order.coupon_code_applied,
            "items": items,
        },
    )


def cart_snapshot(session) -> tuple[dict, Decimal]:
    data = cart_mod.get_cart(session)
    company = CompanySettings.load()
    subtotal, _tax, _total = cart_mod.cart_totals(
        session,
        company.default_tax_rate,
    )
    return data, subtotal


def save_cart_for_recovery(
    request,
    *,
    name: str,
    email: str,
    phone: str = "",
) -> SavedCart:
    if not request.session.session_key:
        request.session.create()
    data, subtotal = cart_snapshot(request.session)
    saved = (
        SavedCart.objects.filter(
            session_key=request.session.session_key,
            email__iexact=email,
            status=SavedCart.STATUS_ACTIVE,
        )
        .order_by("-created_at")
        .first()
    ) or SavedCart(
        session_key=request.session.session_key,
        email=email,
    )
    saved.customer_name = name
    saved.email = email.strip().lower()
    saved.phone = phone
    saved.cart_data = data
    saved.subtotal = subtotal
    saved.last_activity = timezone.now()
    saved.first_reminder_sent_at = None
    saved.second_reminder_sent_at = None
    saved.status = SavedCart.STATUS_ACTIVE
    saved.save()
    request.session["growth_saved_cart_id"] = saved.pk
    request.session.modified = True
    return saved


def touch_saved_cart(request) -> None:
    if not request.session.session_key:
        return
    data, subtotal = cart_snapshot(request.session)
    SavedCart.objects.filter(
        session_key=request.session.session_key,
        status=SavedCart.STATUS_ACTIVE,
    ).update(
        cart_data=data,
        subtotal=subtotal,
        last_activity=timezone.now(),
        first_reminder_sent_at=None,
        second_reminder_sent_at=None,
    )


def saved_cart_recovery_url(saved: SavedCart) -> str:
    return absolute_public_url(saved.get_recovery_path())


def saved_cart_unsubscribe_url(saved: SavedCart) -> str:
    return absolute_public_url(
        f"/marketing/cart/unsubscribe/{saved.recovery_token}/"
    )


def send_saved_cart_message(
    saved: SavedCart,
    *,
    reminder_number: int = 0,
) -> OutboundEmail:
    company = CompanySettings.load()
    if reminder_number == 0:
        subject = f"Your {company.company_name} cart has been saved"
        opening = "Your selected items have been saved."
    elif reminder_number == 1:
        subject = f"Complete your {company.company_name} order"
        opening = "You still have items waiting in your saved cart."
    else:
        subject = f"Final reminder about your {company.company_name} cart"
        opening = "This is the final reminder for your saved cart."
    unsubscribe_url = saved_cart_unsubscribe_url(saved)
    body = (
        f"Hello {saved.customer_name or 'there'},\n\n"
        f"{opening}\n\n"
        f"Resume your cart: {saved_cart_recovery_url(saved)}\n\n"
        f"Saved subtotal: {company.currency_code} {saved.subtotal:.2f}\n\n"
        "Availability and prices may change before checkout. You received this "
        "because you asked LEOSOFT to save and remind you about the cart.\n\n"
        f"Stop reminders: {unsubscribe_url}"
    )
    activity_stamp = int(saved.last_activity.timestamp())
    return send_outbound_email(
        to_email=saved.email,
        subject=subject,
        body=body,
        created_by=None,
        category=OutboundEmail.CATEGORY_MARKETING,
        idempotency_key=(
            f"saved-cart:{saved.pk}:{activity_stamp}:reminder:{reminder_number}"
        ),
        extra_headers={"List-Unsubscribe": f"<{unsubscribe_url}>"},
    )


def restore_saved_cart(request, saved: SavedCart) -> None:
    cart_mod.set_cart(request.session, saved.cart_data or {})
    request.session["growth_saved_cart_id"] = saved.pk
    request.session.modified = True


def recalculate_ambassador_totals(ambassador: Ambassador) -> None:
    click_count = ambassador.clicks.count()
    lead_count = ambassador.attributed_leads.count()
    conversion_summary = ambassador.conversions.exclude(
        status=AmbassadorConversion.STATUS_CANCELLED
    ).aggregate(order_count=Count("id"), revenue_total=Sum("revenue"))
    Ambassador.objects.filter(pk=ambassador.pk).update(
        click_count=click_count,
        lead_count=lead_count,
        order_count=conversion_summary["order_count"] or 0,
        revenue_total=conversion_summary["revenue_total"] or Decimal("0"),
    )


def mark_order_growth_attribution(request, order) -> None:
    if request.session.session_key:
        SavedCart.objects.filter(
            session_key=request.session.session_key,
            status=SavedCart.STATUS_ACTIVE,
        ).update(
            status=SavedCart.STATUS_RECOVERED,
            recovered_order=order,
            last_activity=timezone.now(),
        )

    ambassador_code = request.session.get(AMBASSADOR_SESSION_KEY)
    ambassador = (
        Ambassador.objects.filter(code=ambassador_code, is_active=True).first()
        if ambassador_code
        else None
    )
    if ambassador:
        _conversion, created = AmbassadorConversion.objects.get_or_create(
            order=order,
            defaults={
                "ambassador": ambassador,
                "revenue": order.total,
                "commission_amount": ambassador.calculate_commission(order.total),
            },
        )
        if created:
            recalculate_ambassador_totals(ambassador)
    request.session[PURCHASE_SESSION_KEY] = order.reference
    request.session.modified = True


def attribute_lead_to_ambassador(request, lead) -> None:
    ambassador_code = request.session.get(AMBASSADOR_SESSION_KEY)
    ambassador = (
        Ambassador.objects.filter(code=ambassador_code, is_active=True).first()
        if ambassador_code
        else None
    )
    if not ambassador:
        return
    _row, created = AmbassadorLead.objects.get_or_create(
        lead=lead,
        defaults={"ambassador": ambassador},
    )
    if created:
        recalculate_ambassador_totals(ambassador)
        lead.source = f"ambassador:{ambassador.code}"[:60]
        lead.medium = "referral"
        lead.save(update_fields=["source", "medium", "updated_at"])


def generate_content_assets(
    *,
    product,
    campaign=None,
    created_by=None,
) -> list[ContentAsset]:
    company = CompanySettings.load()
    growth = GrowthSettings.load()
    price = product.min_active_variant_price or product.price
    url = absolute_public_url(product.get_absolute_url())
    description = (
        product.short_description
        or " ".join(product.description.split())[:220]
        or product.category.name
    )
    hashtags = growth.default_content_hashtags.strip()
    availability = (
        "Available now" if product.available_to_sell else "Ask for availability"
    )
    currency = company.currency_code
    drafts = [
        (
            ContentAsset.TYPE_WHATSAPP,
            f"WhatsApp — {product.name}",
            f"{product.name}\n{description}\n{availability} · {currency} "
            f"{price}\n{url}\n{hashtags}",
        ),
        (
            ContentAsset.TYPE_SOCIAL_CAPTION,
            f"Social caption — {product.name}",
            f"Looking for {product.name}? {description} {availability}. Price: "
            f"{currency} {price}. View details or order from LEOSOFT UG LTD: "
            f"{url}\n\n{hashtags}",
        ),
        (
            ContentAsset.TYPE_TIKTOK_SCRIPT,
            f"Short-video script — {product.name}",
            f"HOOK: Before you buy your next {product.category.name.lower()}, "
            f"look at this.\nSHOW: Display {product.name} from several angles "
            f"and demonstrate one useful feature.\nVALUE: {description}\nPRICE: "
            f"{currency} {price}.\nCTA: Visit leosoftug.com or contact LEOSOFT "
            f"UG LTD for availability, warranty and delivery.\nON-SCREEN: {url}",
        ),
        (
            ContentAsset.TYPE_LINKEDIN,
            f"LinkedIn — {product.name}",
            f"LEOSOFT UG LTD is offering {product.name} for professionals, "
            f"businesses and institutions that need dependable technology. "
            f"{description} Pricing starts at {currency} {price}. Product "
            f"details and enquiries: {url}\n\n{hashtags}",
        ),
        (
            ContentAsset.TYPE_EMAIL,
            f"Email — {product.name}",
            f"Subject: Discover {product.name} from LEOSOFT UG LTD\n\nHello,"
            f"\n\n{description}\n\nPrice: {currency} {price}\nStatus: "
            f"{availability}\n\nView the product and request assistance: {url}"
            "\n\nRegards,\nLEOSOFT UG LTD",
        ),
        (
            ContentAsset.TYPE_POSTER,
            f"Poster copy — {product.name}",
            f"{product.name.upper()}\n{description}\n{currency} {price}\n"
            f"{availability.upper()}\nSHOP OR ENQUIRE: {url}\nLEOSOFT UG LTD "
            "— Reliable technology and support.",
        ),
    ]
    return [
        ContentAsset.objects.create(
            product=product,
            campaign=campaign,
            asset_type=asset_type,
            title=title,
            body=body,
            created_by=created_by,
        )
        for asset_type, title, body in drafts
    ]


def _accepted_or_suppressed(log: OutboundEmail) -> bool:
    return log.status in {
        OutboundEmail.STATUS_SENT,
        OutboundEmail.STATUS_DELIVERED,
        OutboundEmail.STATUS_SUPPRESSED,
    }


def process_saved_cart_reminders(*, limit: int = 100) -> dict:
    config = GrowthSettings.load()
    if not config.abandoned_cart_enabled:
        return {"first": 0, "second": 0, "errors": 0}
    now = timezone.now()
    first_cutoff = now - timezone.timedelta(
        hours=config.abandoned_cart_first_delay_hours
    )
    second_cutoff = now - timezone.timedelta(
        hours=config.abandoned_cart_second_delay_hours
    )
    first_sent = second_sent = errors = 0

    first_rows = SavedCart.objects.filter(
        status=SavedCart.STATUS_ACTIVE,
        first_reminder_sent_at__isnull=True,
        last_activity__lte=first_cutoff,
    ).order_by("last_activity")[:limit]
    for saved in first_rows:
        log = send_saved_cart_message(saved, reminder_number=1)
        if _accepted_or_suppressed(log):
            saved.first_reminder_sent_at = now
            saved.save(update_fields=["first_reminder_sent_at", "updated_at"])
            first_sent += int(log.status != OutboundEmail.STATUS_SUPPRESSED)
        else:
            errors += 1

    second_rows = SavedCart.objects.filter(
        status=SavedCart.STATUS_ACTIVE,
        first_reminder_sent_at__isnull=False,
        first_reminder_sent_at__lte=second_cutoff,
        second_reminder_sent_at__isnull=True,
    ).order_by("first_reminder_sent_at")[:limit]
    for saved in second_rows:
        log = send_saved_cart_message(saved, reminder_number=2)
        if _accepted_or_suppressed(log):
            saved.second_reminder_sent_at = now
            saved.save(update_fields=["second_reminder_sent_at", "updated_at"])
            second_sent += int(log.status != OutboundEmail.STATUS_SUPPRESSED)
        else:
            errors += 1
    return {"first": first_sent, "second": second_sent, "errors": errors}


def stock_alert_reason(subscription: StockAlertSubscription) -> tuple[bool, str]:
    product = subscription.product
    price = product.min_active_variant_price or product.price
    company = CompanySettings.load()
    if (
        subscription.alert_type == StockAlertSubscription.ALERT_BACK_IN_STOCK
        and product.available_to_sell
    ):
        return True, "is back in stock"
    if (
        subscription.alert_type == StockAlertSubscription.ALERT_PRICE_DROP
        and subscription.target_price is not None
        and price <= subscription.target_price
    ):
        return True, f"is now {company.currency_code} {price}"
    return False, ""


def send_stock_alert_message(
    subscription: StockAlertSubscription,
    *,
    reason: str,
) -> OutboundEmail:
    product = subscription.product
    company = CompanySettings.load()
    unsubscribe_url = absolute_public_url(
        f"/marketing/alerts/unsubscribe/{subscription.token}/"
    )
    body = (
        f"Hello,\n\n{product.name} {reason}.\n\nView it here: "
        f"{absolute_public_url(product.get_absolute_url())}\n\n"
        "Availability can change quickly, so please confirm before payment.\n\n"
        f"Stop this alert: {unsubscribe_url}"
    )
    product_stamp = int(product.updated_at.timestamp())
    return send_outbound_email(
        to_email=subscription.email,
        subject=f"{product.name} update from {company.company_name}",
        body=body,
        created_by=None,
        category=OutboundEmail.CATEGORY_MARKETING,
        idempotency_key=f"stock-alert:{subscription.pk}:{product_stamp}",
        extra_headers={"List-Unsubscribe": f"<{unsubscribe_url}>"},
    )


def process_stock_alerts(*, limit: int = 100) -> dict:
    config = GrowthSettings.load()
    if not config.back_in_stock_enabled:
        return {"sent": 0, "errors": 0}
    sent = errors = 0
    subscriptions = StockAlertSubscription.objects.filter(
        is_active=True
    ).select_related("product", "product__category")[:limit]
    for subscription in subscriptions:
        triggered, reason = stock_alert_reason(subscription)
        if not triggered:
            continue
        log = send_stock_alert_message(subscription, reason=reason)
        if _accepted_or_suppressed(log):
            subscription.is_active = False
            subscription.notified_at = timezone.now()
            subscription.save(update_fields=["is_active", "notified_at"])
            sent += int(log.status != OutboundEmail.STATUS_SUPPRESSED)
        else:
            errors += 1
    return {"sent": sent, "errors": errors}
