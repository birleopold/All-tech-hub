from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

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
    brand: str
    condition_code: str
    condition_label: str
    display_price: Decimal
    display_compare_at_price: Decimal | None
    savings_amount: Decimal | None
    savings_percent: int | None

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

    @property
    def public_brand(self) -> str:
        return self.brand

    @property
    def public_condition(self) -> str:
        return self.condition_label

    @property
    def public_price(self) -> Decimal:
        return self.display_price

    @property
    def public_compare_at_price(self) -> Decimal | None:
        return self.display_compare_at_price


def prepare_public_products(products: Iterable[Product]) -> list[PublicProductCard]:
    """Build public proxies using already-prefetched relations.

    Product cards historically called model helpers that issued filtered related
    queries for every item. These proxies calculate image, price, condition,
    discount, variant and stock values in memory so public grids remain fast as
    the catalogue grows.
    """

    prepared: list[PublicProductCard] = []
    for product in products:
        gallery_images = sorted(
            (image for image in product.gallery_images.all() if image.image),
            key=lambda image: (image.sort_order, image.pk or 0),
        )
        active_variants = sorted(
            (variant for variant in product.variants.all() if variant.is_active),
            key=lambda variant: (variant.price, variant.sort_order, variant.pk or 0),
        )
        has_variants = bool(active_variants)
        min_price = active_variants[0].price if active_variants else None

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

        try:
            growth_data = product.growth_data
        except ObjectDoesNotExist:
            growth_data = None

        brand = (getattr(growth_data, "brand", "") or "").strip()
        condition_code = (getattr(growth_data, "condition", "") or "").strip()
        condition_label = (
            growth_data.get_condition_display() if growth_data and condition_code else ""
        )

        display_price = min_price if min_price is not None else product.price
        compare_at = None
        if active_variants:
            cheapest_variant = active_variants[0]
            if (
                cheapest_variant.compare_at_price is not None
                and cheapest_variant.compare_at_price > cheapest_variant.price
            ):
                compare_at = cheapest_variant.compare_at_price
        if (
            compare_at is None
            and product.compare_at_price is not None
            and product.compare_at_price > display_price
        ):
            compare_at = product.compare_at_price

        savings_amount = compare_at - display_price if compare_at else None
        savings_percent = (
            max(1, round((savings_amount / compare_at) * 100))
            if savings_amount and compare_at
            else None
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
                brand=brand,
                condition_code=condition_code,
                condition_label=condition_label,
                display_price=display_price,
                display_compare_at_price=compare_at,
                savings_amount=savings_amount,
                savings_percent=savings_percent,
            )
        )

    return prepared
