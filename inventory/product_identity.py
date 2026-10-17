"""Catalogue SKU integrity shared between server validation and staff UI."""
from django.db.models.functions import Lower, Trim
from django.urls import reverse

from catalog.models import Product, ProductVariant


def normal_sku(sku):
    return (sku or "").strip().lower()


def conflicting_sku(sku, *, exclude_product=None, exclude_variant=None):
    token = normal_sku(sku)
    if not token:
        return None
    products = Product.objects.alias(canonical=Lower(Trim("sku"))).filter(canonical=token)
    if exclude_product:
        products = products.exclude(pk=exclude_product)
    match = products.order_by("pk").first()
    if match:
        return {"name": match.name, "sku": match.sku,
                "url": reverse("staff_product_edit", args=[match.pk])}
    variants = ProductVariant.objects.alias(canonical=Lower(Trim("sku"))).filter(
        canonical=token
    ).select_related("product")
    if exclude_variant:
        variants = variants.exclude(pk=exclude_variant)
    match = variants.order_by("pk").first()
    if match:
        return {"name": f"{match.product.name} / {match.name}", "sku": match.sku,
                "url": reverse("staff_product_edit", args=[match.product_id])}
    return None


def same_name_products(name, *, exclude_product=None):
    normalized = (name or "").strip().lower()
    if len(normalized) < 3:
        return []
    query = Product.objects.alias(canonical=Lower(Trim("name"))).filter(
        canonical=normalized
    ).order_by("pk")
    if exclude_product:
        query = query.exclude(pk=exclude_product)
    return [{"name": item.name, "sku": item.sku,
             "url": reverse("staff_product_edit", args=[item.pk])}
            for item in query[:5]]
