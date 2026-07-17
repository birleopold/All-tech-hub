from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse

from catalog.models import Product, ProductReview
from commerce import cart as cart_mod
from commerce.customer_messages import _deliver
from commerce.models import Order
from core.models import CompanySettings
from growth.models import GrowthSettings


REVIEW_SUBJECT_PREFIX = "Review your order"
TERMINAL_REVIEW_STATUSES = {Order.STATUS_DELIVERED, Order.STATUS_FULFILLED}


def _absolute_public_url(path: str) -> str:
    company = CompanySettings.load()
    base = (company.website or "https://leosoftug.com").rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def order_product_review_path(order: Order, product_id: int) -> str:
    return reverse(
        "order_product_review",
        kwargs={
            "reference": order.reference,
            "view_key": order.view_key,
            "product_id": product_id,
        },
    )


def order_review_subject(order: Order) -> str:
    return f"{REVIEW_SUBJECT_PREFIX} {order.reference}"


def reviewable_products(order: Order) -> list[Product]:
    products: list[Product] = []
    seen: set[int] = set()
    lines = order.lines.select_related("product").order_by("id")
    for line in lines:
        product = line.product
        if (
            product is None
            or product.pk in seen
            or product.kind != Product.KIND_PHYSICAL
            or not product.is_published
        ):
            continue
        seen.add(product.pk)
        products.append(product)
    return products


def send_order_review_request(order: Order):
    if not getattr(settings, "ORDER_CUSTOMER_EMAILS_ENABLED", True):
        return None
    if not getattr(settings, "ORDER_REVIEW_EMAILS_ENABLED", False):
        return None

    order = Order.objects.select_related("customer").prefetch_related(
        "lines__product"
    ).get(pk=order.pk)
    if order.status not in TERMINAL_REVIEW_STATUSES:
        return None

    products = reviewable_products(order)
    if not products:
        return None

    company = CompanySettings.load()
    growth = GrowthSettings.load()
    links = "\n".join(
        f"- {product.name}: "
        f"{_absolute_public_url(order_product_review_path(order, product.pk))}"
        for product in products
    )
    google_review = ""
    if growth.google_review_url:
        google_review = (
            "\nYou can also review the overall LEOSOFT experience on Google:\n"
            f"{growth.google_review_url}\n"
        )

    body = (
        f"Hello {order.contact_name},\n\n"
        f"Thank you for choosing {company.company_name}. Your order "
        f"{order.reference} is complete.\n\n"
        "Your feedback helps other customers make informed decisions and helps "
        "our team improve. Use the private verified-purchase links below:\n\n"
        f"{links}\n"
        f"{google_review}\n"
        "Reviews are moderated before publication. Please do not forward the "
        "private links because they are connected to your order.\n\n"
        f"Regards,\n{company.company_name}"
    )
    return _deliver(
        to_email=order.contact_email,
        subject=order_review_subject(order),
        body=body,
    )


def send_order_review_request_by_id(order_id: int):
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return None
    return send_order_review_request(order)


def verified_review_for_order(
    *,
    order: Order,
    product: Product,
    rating: int,
    title: str,
    body: str,
) -> ProductReview:
    if order.status not in TERMINAL_REVIEW_STATUSES:
        raise ValueError("Reviews are available after the order is delivered or fulfilled.")
    if not order.lines.filter(product=product).exists():
        raise ValueError("This product is not part of the order.")
    if rating < 1 or rating > 5 or not body.strip():
        raise ValueError("Enter a rating from 1 to 5 and a short review.")

    existing = (
        ProductReview.objects.filter(
            product=product,
            customer=order.customer,
            is_verified_purchase=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if existing:
        existing.author_name = order.contact_name[:120]
        existing.rating = rating
        existing.title = title.strip()[:200]
        existing.body = body.strip()[:1000]
        existing.is_published = False
        existing.moderated_at = None
        existing.moderated_by = None
        existing.save()
        return existing

    return ProductReview.objects.create(
        product=product,
        customer=order.customer,
        author_name=order.contact_name[:120],
        rating=rating,
        title=title.strip()[:200],
        body=body.strip()[:1000],
        is_published=False,
        is_verified_purchase=True,
    )


def reorder_into_cart(session, order: Order) -> dict[str, int]:
    added_rows = added_quantity = skipped_rows = 0
    lines = order.lines.select_related("product", "product_variant")
    for line in lines:
        product = line.product
        variant = line.product_variant
        if (
            product is None
            or not product.is_published
            or product.kind != Product.KIND_PHYSICAL
        ):
            skipped_rows += 1
            continue

        quantity = max(1, int(line.quantity))
        if variant is not None:
            if not variant.is_active or not variant.available_to_sell:
                skipped_rows += 1
                continue
            if variant.track_inventory:
                quantity = min(quantity, int(variant.stock_quantity))
            if quantity <= 0:
                skipped_rows += 1
                continue
            cart_mod.add_variant(session, variant.pk, quantity)
        else:
            if product.has_sellable_variants() or not product.available_to_sell:
                skipped_rows += 1
                continue
            if product.track_inventory:
                quantity = min(quantity, int(product.stock_quantity))
            if quantity <= 0:
                skipped_rows += 1
                continue
            cart_mod.add_product(session, product.pk, quantity)

        added_rows += 1
        added_quantity += quantity

    return {
        "added_rows": added_rows,
        "added_quantity": added_quantity,
        "skipped_rows": skipped_rows,
    }
