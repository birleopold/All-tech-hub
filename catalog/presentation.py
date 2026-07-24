from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from catalog.models import Product


@dataclass(slots=True)
class PublicProductCard:
    """Read-only template proxy with precomputed public presentation values."""

    product: Product
    primary_display_image: Any
    has_sellable_variants: bool
    min_active_variant_price: Decimal | None
    active_variant_count: int
    available_to_sell: bool
    is_low_stock: bool

    def __getattr__(self, name: str):
        return getattr(self.product, name)

    # Public-page aliases keep detailed templates explicit while retaining the
    # original card attribute names used by the homepage and catalogue.
    @property
    def public_display_image(self):
        return self.primary_display_image

    @property
    def public_has_variants(self) -> bool:
        return self.has_sellable_variants

    @property
    def public_min_price(self) -> Decimal | None:
        return self.min_active_variant_price

    @property
    def public_variant_count(self) -> int:
        return self.active_variant_count

    @property
    def public_available(self) -> bool:
        return self.available_to_sell

    @property
    def public_low_stock(self) -> bool:
        return self.is_low_stock


def prepare_public_products(products: Iterable[Product]) -> list[PublicProductCard]:
    """Build card proxies using already-prefetched relations.

    Public templates historically called model helpers that issue filtered related
    queries for every card. These proxies calculate image, variant, stock and price
    values in memory so homepage and catalogue grids remain fast as inventory grows.
    """

    prepared: list[PublicProductCard] = []
    for product in products:
        gallery_images = sorted(
            (image for image in product.gallery_images.all() if image.image),
            key=lambda image: (image.sort_order, image.pk or 0),
        )
        active_variants = [
            variant for variant in product.variants.all() if variant.is_active
        ]
        has_variants = bool(active_variants)
        min_price = (
            min(variant.price for variant in active_variants)
            if active_variants
            else None
        )

        if product.kind == Product.KIND_SERVICE:
            available = True
            low_stock = False
        elif active_variants:
            available = any(
                (not variant.track_inventory) or variant.stock_quantity > 0
                for variant in active_variants
            )
            tracked_variants = [
                variant for variant in active_variants if variant.track_inventory
            ]
            low_stock = bool(
                product.reorder_level > 0
                and tracked_variants
                and any(
                    variant.stock_quantity <= product.reorder_level
                    for variant in tracked_variants
                )
            )
        else:
            available = (not product.track_inventory) or product.stock_quantity > 0
            low_stock = bool(
                product.track_inventory
                and product.reorder_level > 0
                and product.stock_quantity <= product.reorder_level
            )

        prepared.append(
            PublicProductCard(
                product=product,
                primary_display_image=(
                    gallery_images[0].image
                    if gallery_images
                    else product.image if product.image else None
                ),
                has_sellable_variants=has_variants,
                min_active_variant_price=min_price,
                active_variant_count=len(active_variants),
                available_to_sell=available,
                is_low_stock=low_stock,
            )
        )

    return prepared
