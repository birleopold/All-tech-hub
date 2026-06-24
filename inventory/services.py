from django.core.exceptions import ValidationError
from django.db import models, transaction

from catalog.models import Product, ProductVariant
from inventory.models import StockMovement


def current_stock(*, product, product_variant=None) -> int:
    model = ProductVariant if product_variant is not None else Product
    pk = product_variant.pk if product_variant is not None else product.pk
    return int(model.objects.values_list("stock_quantity", flat=True).get(pk=pk))


def record_stock_movement(
    *,
    product,
    quantity_delta,
    movement_type,
    product_variant=None,
    reference="",
    note="",
    actor=None,
    adjustment=None,
):
    return StockMovement.objects.create(
        product=product,
        product_variant=product_variant,
        quantity_delta=int(quantity_delta),
        balance_after=current_stock(product=product, product_variant=product_variant),
        movement_type=movement_type,
        reference=reference[:64],
        note=note[:255],
        actor=actor,
        adjustment=adjustment,
    )


@transaction.atomic
def change_stock(
    *,
    product,
    quantity_delta,
    movement_type,
    product_variant=None,
    reference="",
    note="",
    actor=None,
):
    delta = int(quantity_delta)
    model = ProductVariant if product_variant is not None else Product
    pk = product_variant.pk if product_variant is not None else product.pk
    qs = model.objects.select_for_update().filter(pk=pk)
    if delta < 0:
        qs = qs.filter(stock_quantity__gte=-delta)
    if qs.update(stock_quantity=models.F("stock_quantity") + delta) != 1:
        raise ValidationError("Insufficient stock for this movement.")
    return record_stock_movement(
        product=product,
        product_variant=product_variant,
        quantity_delta=delta,
        movement_type=movement_type,
        reference=reference,
        note=note,
        actor=actor,
    )
