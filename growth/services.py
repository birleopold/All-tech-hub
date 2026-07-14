from decimal import Decimal
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
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

ANALYTICS_SESSION_KEY = "growth_analytics_events"
PURCHASE_SESSION_KEY = "growth_purchase_order"
AMBASSADOR_SESSION_KEY = "growth_ambassador_code"


def company_base_url() -> str:
    company = CompanySettings.load()
    return (company.website or "https://leosoftug.com").rstrip("/") + "/"


def absolute_public_url(path: str) -> str:
    return urljoin(company_base_url(), path.lstrip("/"))


def _product_growth_data(product: Product):
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
    metadata = _product_growth_data(product)
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
    items = [
        analytics_item(
            line.product,
            variant=line.product_variant,
            quantity=line.quantity,
        )
        if line.product
        else {
            "item_id": line.sku or str(line.pk),
            "item_name": line.description,
            "price": float(line.unit_price),
            "quantity": line.quantity,
        }
        for line in order.lines.select_related(
            "product", "product__category", "product_variant"
        )
    ]
    return analytics_event(
        "purchase",
        {
            "transaction_id": order.reference,
            "value": float(order.total),
            "tax": float(order.tax_amount),
            "shipping": 0,
            "currency": company.currency_code,
            "coupon": order.coupon_code_applied,
            "items": items,
        },
    )


def cart_snapshot(session) -> tuple[dict, Decimal]:
    data = cart_mod.get_cart(session)
    company = CompanySettings.load()
    subtotal, _tax, _total = cart_mod.cart_totals(
        session, company.default_tax_rate
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
    )
    if saved is None:
        saved = SavedCart(
            session_key=request.session.session_key,
            email=email,
        )
    saved.customer_name = name
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
) -> int:
    company = CompanySettings.load()
    url = saved_cart_recovery_url(saved)
    unsubscribe_url = saved_cart_unsubscribe_url(saved)
    if reminder_number == 0:
        subject = f"Your {company.company_name} cart has been saved"
        opening = "Your selected items have been saved."
    elif reminder_number == 1:
        subject = f"Complete your {company.company_name} order"
        opening = "You still have items waiting in your saved cart."
    else:
        subject = f"Final reminder about your {company.company_name} cart"
        opening = "This is the final reminder for your saved cart."
    body = (
        f"Hello {saved.customer_name or 'there'},\n\n"
        f"{opening}\n\n"
        f"Resume your cart: {url}\n\n"
        f"Saved subtotal: {company.currency_code} {saved.subtotal:.2f}\n\n"
        "Availability and prices may change before checkout. "
        "You received this because you asked LEOSOFT to save and remind you "
        f"about the cart.\n\nStop reminders: {unsubscribe_url}"
    )
    return send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [saved.email],
        fail_silently=False,
    )


def restore_saved_cart(request, saved: SavedCart) -> None:
    cart_mod.set_cart(request.session, saved.cart_data or {})
    request.session["growth_saved_cart_id"] = saved.pk
    request.session.modified = True


def mark_order_growth_attribution(request, order) -> None:
    session_key = request.session.session_key
    if session_key:
        SavedCart.objects.filter(
            session_key=session_key,
            status=SavedCart.STATUS_ACTIVE,
        ).update(
            status=SavedCart.STATUS_RECOVERED,
            recovered_order=order,
            last_activity=timezone.now(),
        )

    ambassador_code = request.session.get(AMBASSADOR_SESSION_KEY)
    if ambassador_code:
        ambassador = Ambassador.objects.filter(
            code=ambassador_code,
            is_active=True,
        ).first()
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
                Ambassador.objects.filter(pk=ambassador.pk).update(
                    order_count=F("order_count") + 1,
                    revenue_total=F("revenue_total") + order.total,
                )
    request.session[PURCHASE_SESSION_KEY] = order.reference
    request.session.modified = True


def attribute_lead_to_ambassador(request, lead) -> None:
    ambassador_code = request.session.get(AMBASSADOR_SESSION_KEY)
    if not ambassador_code:
        return
    ambassador = Ambassador.objects.filter(
        code=ambassador_code,
        is_active=True,
    ).first()
    if not ambassador:
        return
    _row, created = AmbassadorLead.objects.get_or_create(
        lead=lead,
        defaults={"ambassador": ambassador},
    )
    if created:
        Ambassador.objects.filter(pk=ambassador.pk).update(
            lead_count=F("lead_count") + 1
        )
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
            f"{product.name}\n{description}\n{availability} · "
            f"{currency} {price}\n{url}\n{hashtags}",
        ),
        (
            ContentAsset.TYPE_SOCIAL_CAPTION,
            f"Social caption — {product.name}",
            f"Looking for {product.name}? {description} {availability}. "
            f"Price: {currency} {price}. View details or order from "
            f"LEOSOFT UG LTD: {url}\n\n{hashtags}",
        ),
        (
            ContentAsset.TYPE_TIKTOK_SCRIPT,
            f"Short-video script — {product.name}",
            f"HOOK: Before you buy your next {product.category.name.lower()}, "
            "look at this.\n"
            f"SHOW: Display {product.name} from several angles and demonstrate "
            "one useful feature.\n"
            f"VALUE: {description}\nPRICE: {currency} {price}.\n"
            "CTA: Visit leosoftug.com or contact LEOSOFT UG LTD for "
            f"availability, warranty and delivery.\nON-SCREEN: {url}",
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
            f"Subject: Discover {product.name} from LEOSOFT UG LTD\n\n"
            f"Hello,\n\n{description}\n\nPrice: {currency} {price}\n"
            f"Status: {availability}\n\nView the product and request "
            f"assistance: {url}\n\nRegards,\nLEOSOFT UG LTD",
        ),
        (
            ContentAsset.TYPE_POSTER,
            f"Poster copy — {product.name}",
            f"{product.name.upper()}\n{description}\n{currency} {price}\n"
            f"{availability.upper()}\nSHOP OR ENQUIRE: {url}\n"
            "LEOSOFT UG LTD — Reliable technology and support.",
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
        try:
            send_saved_cart_message(saved, reminder_number=1)
            saved.first_reminder_sent_at = now
            saved.save(update_fields=["first_reminder_sent_at", "updated_at"])
            first_sent += 1
        except Exception:
            errors += 1

    second_rows = SavedCart.objects.filter(
        status=SavedCart.STATUS_ACTIVE,
        first_reminder_sent_at__isnull=False,
        second_reminder_sent_at__isnull=True,
        last_activity__lte=second_cutoff,
    ).order_by("last_activity")[:limit]
    for saved in second_rows:
        try:
            send_saved_cart_message(saved, reminder_number=2)
            saved.second_reminder_sent_at = now
            saved.save(update_fields=["second_reminder_sent_at", "updated_at"])
            second_sent += 1
        except Exception:
            errors += 1
    return {"first": first_sent, "second": second_sent, "errors": errors}


def process_stock_alerts(*, limit: int = 100) -> dict:
    config = GrowthSettings.load()
    if not config.back_in_stock_enabled:
        return {"sent": 0, "errors": 0}
    company = CompanySettings.load()
    sent = errors = 0
    subscriptions = StockAlertSubscription.objects.filter(
        is_active=True
    ).select_related("product", "product__category")[:limit]
    for subscription in subscriptions:
        product = subscription.product
        price = product.min_active_variant_price or product.price
        triggered = False
        reason = ""
        if (
            subscription.alert_type
            == StockAlertSubscription.ALERT_BACK_IN_STOCK
            and product.available_to_sell
        ):
            triggered = True
            reason = "is back in stock"
        elif (
            subscription.alert_type == StockAlertSubscription.ALERT_PRICE_DROP
            and subscription.target_price is not None
            and price <= subscription.target_price
        ):
            triggered = True
            reason = f"is now {company.currency_code} {price}"
        if not triggered:
            continue
        url = absolute_public_url(product.get_absolute_url())
        unsubscribe_url = absolute_public_url(
            f"/marketing/alerts/unsubscribe/{subscription.token}/"
        )
        try:
            send_mail(
                f"{product.name} update from {company.company_name}",
                (
                    f"Hello,\n\n{product.name} {reason}.\n\n"
                    f"View it here: {url}\n\n"
                    "Availability can change quickly, so please confirm before "
                    f"payment.\n\nStop this alert: {unsubscribe_url}"
                ),
                settings.DEFAULT_FROM_EMAIL,
                [subscription.email],
                fail_silently=False,
            )
            subscription.is_active = False
            subscription.notified_at = timezone.now()
            subscription.save(update_fields=["is_active", "notified_at"])
            sent += 1
        except Exception:
            errors += 1
    return {"sent": sent, "errors": errors}
