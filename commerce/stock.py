"""Checkout-safe stock updates (works with SQLite; stronger guarantees on PostgreSQL with row locks)."""

from __future__ import annotations

from django.db.models import F

from catalog.models import Product, ProductVariant


class InsufficientStock(Exception):
    """Raised when an atomic decrement cannot reserve enough quantity."""


def decrement_line_stock(
    *,
    product: Product,
    variant: ProductVariant | None,
    qty: int,
    reference: str = "",
) -> None:
    if product.kind != Product.KIND_PHYSICAL:
        return
    if qty <= 0:
        return
    if variant is not None:
        if not variant.track_inventory:
            return
        n = ProductVariant.objects.filter(
            pk=variant.pk,
            stock_quantity__gte=qty,
        ).update(stock_quantity=F("stock_quantity") - qty)
        if n != 1:
            raise InsufficientStock(
                f"Not enough stock for “{product.name} ({variant.name})”. Try a lower quantity."
            )
        from inventory.models import StockMovement
        from inventory.services import record_stock_movement

        record_stock_movement(
            product=product,
            product_variant=variant,
            quantity_delta=-qty,
            movement_type=StockMovement.TYPE_SALE,
            reference=reference,
        )
        return
    if not product.track_inventory:
        return
    n = Product.objects.filter(
        pk=product.pk,
        stock_quantity__gte=qty,
    ).update(stock_quantity=F("stock_quantity") - qty)
    if n != 1:
        raise InsufficientStock(
            f"Not enough stock for “{product.name}”. Try a lower quantity."
        )
    from inventory.models import StockMovement
    from inventory.services import record_stock_movement

    record_stock_movement(
        product=product,
        quantity_delta=-qty,
        movement_type=StockMovement.TYPE_SALE,
        reference=reference,
    )
