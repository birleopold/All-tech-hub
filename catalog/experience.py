from django.db.models import Case, IntegerField, When

from catalog.models import Product

RECENT_SESSION_KEY = "catalog_recent_product_ids"
COMPARE_SESSION_KEY = "catalog_compare_product_ids"
MAX_RECENT = 8
MAX_COMPARE = 4


def _normalise_ids(raw, *, maximum: int) -> list[int]:
    values = []
    for item in raw if isinstance(raw, list) else []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in values:
            values.append(value)
        if len(values) >= maximum:
            break
    return values


def recent_ids(request) -> list[int]:
    return _normalise_ids(request.session.get(RECENT_SESSION_KEY, []), maximum=MAX_RECENT)


def compare_ids(request) -> list[int]:
    return _normalise_ids(request.session.get(COMPARE_SESSION_KEY, []), maximum=MAX_COMPARE)


def record_recent_product(request, product: Product) -> None:
    ids = [value for value in recent_ids(request) if value != product.pk]
    ids.insert(0, product.pk)
    request.session[RECENT_SESSION_KEY] = ids[:MAX_RECENT]
    request.session.modified = True


def _ordered_products(ids: list[int]):
    if not ids:
        return Product.objects.none()
    ordering = Case(
        *[When(pk=pk, then=position) for position, pk in enumerate(ids)],
        output_field=IntegerField(),
    )
    return (
        Product.objects.filter(pk__in=ids, is_published=True)
        .select_related("category", "category__parent")
        .prefetch_related("gallery_images", "variants")
        .order_by(ordering)
    )


def recent_products(request, *, exclude_id: int | None = None, limit: int = 4):
    ids = recent_ids(request)
    if exclude_id:
        ids = [value for value in ids if value != exclude_id]
    return list(_ordered_products(ids[: max(0, limit)]))


def compared_products(request):
    return list(
        _ordered_products(compare_ids(request)).filter(kind=Product.KIND_PHYSICAL)
    )


def product_is_compared(request, product_id: int) -> bool:
    return int(product_id) in compare_ids(request)


def toggle_compared_product(request, product: Product) -> tuple[bool, str]:
    ids = compare_ids(request)
    if product.pk in ids:
        ids.remove(product.pk)
        request.session[COMPARE_SESSION_KEY] = ids
        request.session.modified = True
        return False, f"Removed {product.name} from comparison."
    if product.kind != Product.KIND_PHYSICAL:
        return False, "Only physical products can be compared."
    if len(ids) >= MAX_COMPARE:
        return False, f"You can compare up to {MAX_COMPARE} products at a time."
    ids.append(product.pk)
    request.session[COMPARE_SESSION_KEY] = ids
    request.session.modified = True
    return True, f"Added {product.name} to comparison."


def clear_comparison(request) -> None:
    request.session.pop(COMPARE_SESSION_KEY, None)
    request.session.modified = True
