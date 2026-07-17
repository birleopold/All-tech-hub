import uuid

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Product
from commerce.models import Order
from commerce.retention import (
    TERMINAL_REVIEW_STATUSES,
    reorder_into_cart,
    verified_review_for_order,
)


def _secure_order(reference: str, view_key: uuid.UUID) -> Order:
    return get_object_or_404(
        Order.objects.select_related("customer").prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        reference=reference,
        view_key=view_key,
    )


@require_POST
def order_reorder(request, reference: str, view_key: uuid.UUID):
    order = _secure_order(reference, view_key)
    if order.status not in TERMINAL_REVIEW_STATUSES:
        messages.warning(
            request,
            "Reorder is available after the original order is delivered or fulfilled.",
        )
        return redirect(order.get_absolute_url())

    result = reorder_into_cart(request.session, order)
    if result["added_rows"]:
        messages.success(
            request,
            f"Added {result['added_quantity']} available item(s) from {order.reference} to your cart.",
        )
        if result["skipped_rows"]:
            messages.info(
                request,
                f"{result['skipped_rows']} unavailable or changed item(s) were skipped.",
            )
        return redirect("cart")

    messages.warning(
        request,
        "None of the physical products from this order are currently available to reorder.",
    )
    return redirect(order.get_absolute_url())


def order_product_review(
    request,
    reference: str,
    view_key: uuid.UUID,
    product_id: int,
):
    order = _secure_order(reference, view_key)
    product = get_object_or_404(
        Product,
        pk=product_id,
        is_published=True,
        order_lines__order=order,
    )
    if order.status not in TERMINAL_REVIEW_STATUSES:
        messages.warning(
            request,
            "Verified reviews are available after delivery or fulfilment.",
        )
        return redirect(order.get_absolute_url())

    existing_review = (
        product.reviews.filter(
            customer=order.customer,
            is_verified_purchase=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )

    if request.method == "POST":
        try:
            rating = int(request.POST.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0
        try:
            verified_review_for_order(
                order=order,
                product=product,
                rating=rating,
                title=request.POST.get("title") or "",
                body=request.POST.get("body") or "",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                "Thank you. Your verified-purchase review was submitted for moderation.",
            )
            return redirect(order.get_absolute_url())

    return render(
        request,
        "commerce/order_product_review.html",
        {
            "order": order,
            "product": product,
            "existing_review": existing_review,
            "rating_choices": range(5, 0, -1),
        },
    )
