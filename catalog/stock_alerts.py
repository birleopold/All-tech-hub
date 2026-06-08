"""Low-stock helpers for dashboard and inventory views."""

from django.db.models import Q

from catalog.models import Product


def low_stock_products(limit: int | None = 50):
    """Physical products at or below reorder_level (when reorder_level > 0)."""
    qs = (
        Product.objects.filter(
            kind=Product.KIND_PHYSICAL,
            track_inventory=True,
            reorder_level__gt=0,
        )
        .select_related("category")
        .order_by("stock_quantity", "name")
    )
    matches = [p for p in qs if p.is_low_stock]
    if limit is not None:
        return matches[:limit]
    return matches
