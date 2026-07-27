from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.audit import log_audit_event
from merchandising.services import apply_bulk_catalogue_enrichment as apply_base_enrichment


def product_inventory_state(product) -> tuple[bool, bool]:
    """Return whether inventory is managed and whether the product is sellable."""

    active_variants = [variant for variant in product.variants.all() if variant.is_active]
    if active_variants:
        managed = any(variant.track_inventory for variant in active_variants)
        available = any(
            (not variant.track_inventory) or int(variant.stock_quantity) > 0
            for variant in active_variants
        )
        return managed, available
    return bool(product.track_inventory), (
        (not product.track_inventory) or int(product.stock_quantity) > 0
    )


@transaction.atomic
def apply_bulk_catalogue_enrichment(*, products, cleaned_data: dict, actor) -> dict:
    """Apply enrichment and handle unavailable variant-managed products correctly."""

    product_list = list(products)
    unpublish_requested = bool(cleaned_data.get("unpublish_out_of_stock"))
    base_data = dict(cleaned_data)
    base_data["unpublish_out_of_stock"] = False
    result = apply_base_enrichment(
        products=product_list,
        cleaned_data=base_data,
        actor=actor,
    )

    unpublished = 0
    if unpublish_requested:
        now = timezone.now()
        for product in product_list:
            inventory_managed, available = product_inventory_state(product)
            if product.is_published and inventory_managed and not available:
                product.is_published = False
                product.updated_at = now
                product.save(update_fields=["is_published", "updated_at"])
                unpublished += 1
        if unpublished:
            log_audit_event(
                actor=actor,
                verb="catalog.bulk_unpublish_unavailable",
                summary=(
                    f"Unpublished {unpublished} tracked catalogue product(s) with no "
                    "sellable base or active variant stock."
                ),
            )
    result["products_unpublished"] = unpublished
    return result
