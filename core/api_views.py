"""Tiny read-only public JSON API.

Intentionally framework-light (plain Django) — no DRF dependency, no writes,
no auth. Used by client integrations to fetch product catalog and look up an
order by its (reference + view_key) pair.
"""

from decimal import Decimal

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from catalog.models import Product
from commerce.models import Order
from commerce.progress import order_progress


def _money(value) -> str:
    if value is None:
        return "0.00"
    return f"{Decimal(value):.2f}"


def _product_to_dict(product: Product) -> dict:
    image = product.primary_display_image
    return {
        "id": product.pk,
        "name": product.name,
        "sku": product.sku,
        "slug": product.slug,
        "kind": product.kind,
        "category": product.category.name if product.category_id else None,
        "short_description": product.short_description,
        "price": _money(product.price),
        "compare_at_price": _money(product.compare_at_price) if product.compare_at_price else None,
        "in_stock": product.available_to_sell,
        "stock_quantity": product.stock_quantity if product.track_inventory else None,
        "is_featured": product.is_featured,
        "url": product.get_absolute_url(),
        "image_url": image.url if image else None,
    }


@require_GET
@cache_control(public=True, max_age=60)
def api_products(request):
    qs = (
        Product.objects.filter(is_published=True)
        .select_related("category")
        .prefetch_related("gallery_images", "variants")
        .order_by("category__sort_order", "name")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    category = (request.GET.get("category") or "").strip()
    if category:
        qs = qs.filter(category__slug=category)
    try:
        limit = max(1, min(int(request.GET.get("limit") or 50), 100))
    except ValueError:
        limit = 50
    items = [_product_to_dict(p) for p in qs[:limit]]
    return JsonResponse({"count": len(items), "results": items})


@require_GET
def api_product_detail(request, slug: str):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related(
            "gallery_images", "variants"
        ),
        slug=slug,
        is_published=True,
    )
    payload = _product_to_dict(product)
    payload["description"] = product.description
    payload["images"] = [
        image.url
        for image in [product.image, *[item.image for item in product.gallery_images.all()]]
        if image
    ]
    payload["variants"] = [
        {
            "id": v.pk,
            "name": v.name,
            "sku": v.sku,
            "price": _money(v.price),
            "stock_quantity": v.stock_quantity if v.track_inventory else None,
            "in_stock": v.available_to_sell,
            "is_active": v.is_active,
        }
        for v in product.variants.filter(is_active=True).order_by("sort_order", "name")
    ]
    return JsonResponse(payload)


@require_GET
@cache_control(private=True, no_store=True)
def api_order_lookup(request):
    """Look up an order using (reference + view_key) — used by receipt URLs."""

    reference = (request.GET.get("reference") or "").strip()
    view_key = (request.GET.get("view_key") or "").strip()
    if not reference or not view_key:
        return JsonResponse(
            {"error": "Both 'reference' and 'view_key' query parameters are required."},
            status=400,
        )
    try:
        order = (
            Order.objects.select_related("shipment")
            .prefetch_related("lines", "status_events")
            .get(reference=reference, view_key=view_key)
        )
    except (Order.DoesNotExist, ValueError):
        raise Http404("Order not found.")

    progress = order_progress(order)
    shipment = getattr(order, "shipment", None)
    return JsonResponse(
        {
            "reference": order.reference,
            "placed_at": order.placed_at.isoformat() if order.placed_at else None,
            "status": order.status,
            "status_display": order.get_status_display(),
            "subtotal": _money(order.subtotal),
            "tax_amount": _money(order.tax_amount),
            "discount_amount": _money(order.discount_amount),
            "delivery_fee": _money(order.delivery_fee),
            "delivery_zone": order.delivery_zone_name,
            "total": _money(order.total),
            "customer_name": order.contact_name,
            "fulfillment_type": order.fulfillment_type,
            "fulfillment_display": order.get_fulfillment_type_display(),
            "progress": {
                "cancelled": progress["cancelled"],
                "cancellation_reason": progress["cancellation_reason"],
                "steps": [
                    {
                        "status": step["status"],
                        "label": step["label"],
                        "state": step["state"],
                        "occurred_at": (
                            step["occurred_at"].isoformat()
                            if step["occurred_at"]
                            else None
                        ),
                        "note": step["note"],
                    }
                    for step in progress["steps"]
                ],
            },
            "shipment": (
                {
                    "status": shipment.status,
                    "status_display": shipment.get_status_display(),
                    "carrier": shipment.carrier,
                    "tracking_number": shipment.tracking_number,
                    "tracking_url": shipment.tracking_url,
                    "estimated_delivery": (
                        shipment.estimated_delivery.isoformat()
                        if shipment.estimated_delivery
                        else None
                    ),
                    "note": shipment.note,
                }
                if shipment
                else None
            ),
            "items": [
                {
                    "description": line.description,
                    "sku": line.sku,
                    "quantity": str(line.quantity),
                    "unit_price": _money(line.unit_price),
                    "line_total": _money(line.line_total),
                }
                for line in order.lines.all()
            ],
        }
    )
