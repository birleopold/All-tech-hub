from __future__ import annotations

from collections.abc import Iterable

from catalog.models import Product


def prepare_public_products(products: Iterable[Product]) -> list[Product]:
    """Attach card-ready values using already-prefetched relations.

    Public templates previously called model helpers that perform filtered related
    queries for every card. This prepares image, variant, stock and price values in
    memory so homepage and catalogue grids stay fast as the catalogue grows.
    """

    prepared = list(products)
    for product in prepared:
        gallery_images = sorted(
            (
                image
                for image in product.gallery_images.all()
                if image.image
            ),
            key=lambda image: (image.sort_order, image.pk or 0),
        )
        active_variants = [
            variant for variant in product.variants.all() if variant.is_active
        ]

        product.public_display_image = (
            gallery_images[0].image
            if gallery_images
            else product.image if product.image else None
        )
        product.public_has_variants = bool(active_variants)
        product.public_variant_count = len(active_variants)
        product.public_min_price = (
            min(variant.price for variant in active_variants)
            if active_variants
            else None
        )

        if product.kind == Product.KIND_SERVICE:
            product.public_available = True
            product.public_low_stock = False
            continue

        if active_variants:
            product.public_available = any(
                (not variant.track_inventory) or variant.stock_quantity > 0
                for variant in active_variants
            )
            tracked_variants = [
                variant for variant in active_variants if variant.track_inventory
            ]
            product.public_low_stock = bool(
                product.reorder_level > 0
                and tracked_variants
                and any(
                    variant.stock_quantity <= product.reorder_level
                    for variant in tracked_variants
                )
            )
        else:
            product.public_available = (
                (not product.track_inventory) or product.stock_quantity > 0
            )
            product.public_low_stock = bool(
                product.track_inventory
                and product.reorder_level > 0
                and product.stock_quantity <= product.reorder_level
            )

    return prepared
