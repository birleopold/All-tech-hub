from __future__ import annotations

from django.db.models import Case, Count, IntegerField, Q, Value, When

from catalog.models import Product
from commerce.models import Order


def _available_physical_products():
    return (
        Product.objects.filter(
            is_published=True,
            kind=Product.KIND_PHYSICAL,
        )
        .filter(
            Q(track_inventory=False)
            | Q(stock_quantity__gt=0)
            | Q(variants__is_active=True, variants__track_inventory=False)
            | Q(variants__is_active=True, variants__stock_quantity__gt=0)
        )
        .select_related("category")
        .prefetch_related("gallery_images", "variants")
        .distinct()
    )


def recommended_products_for_lines(lines, *, limit: int = 4) -> list[Product]:
    line_list = list(lines)
    product_ids = {
        line.product_id if hasattr(line, "product_id") else line.product.pk
        for line in line_list
        if getattr(line, "product", None)
    }
    category_ids = {
        line.product.category_id
        for line in line_list
        if getattr(line, "product", None) and line.product.category_id
    }
    if not product_ids and not category_ids:
        return []

    category_rank = Case(
        When(category_id__in=category_ids, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    qs = (
        _available_physical_products()
        .exclude(pk__in=product_ids)
        .annotate(
            recommendation_rank=category_rank,
            completed_order_count=Count(
                "order_lines__order",
                filter=~Q(order_lines__order__status=Order.STATUS_CANCELLED),
                distinct=True,
            ),
        )
        .order_by(
            "recommendation_rank",
            "-is_featured",
            "-completed_order_count",
            "-updated_at",
            "name",
        )
    )
    return list(qs[: max(1, min(limit, 8))])


def recommended_products_for_order(order: Order, *, limit: int = 4) -> list[Product]:
    lines = order.lines.select_related("product", "product__category")
    return recommended_products_for_lines(lines, limit=limit)
