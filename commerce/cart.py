"""Session-backed cart: keys ``p:<product_id>`` or ``v:<variant_id>`` (legacy: plain product id = ``p``)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

from catalog.models import Product, ProductVariant

CART_SESSION_KEY = "alltech_cart"
COUPON_SESSION_KEY = "alltech_coupon"


@dataclass(frozen=True)
class CartLine:
    product: Product
    variant: ProductVariant | None
    quantity: int

    @property
    def row_key(self) -> str:
        if self.variant is not None:
            return f"v:{self.variant.pk}"
        return f"p:{self.product.pk}"

    @property
    def unit_price(self) -> Decimal:
        if self.variant is not None:
            return self.variant.price
        return self.product.price

    @property
    def label(self) -> str:
        if self.variant is not None:
            return f"{self.product.name} — {self.variant.name}"
        return self.product.name

    @property
    def qty_field_name(self) -> str:
        return "qty_" + self.row_key.replace(":", "_")


def _cart_dict(session: dict[str, Any]) -> dict[str, int]:
    raw = session.get(CART_SESSION_KEY)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            q = int(v)
            if q > 0:
                out[str(k)] = q
        except (TypeError, ValueError):
            continue
    return out


def normalize_line_key(raw: str) -> tuple[str, int] | None:
    s = str(raw).strip()
    if not s:
        return None
    if ":" in s:
        kind, _, rest = s.partition(":")
        kind = kind.lower().strip()
        if kind in ("p", "v") and rest.isdigit():
            return kind, int(rest)
        return None
    if s.isdigit():
        return "p", int(s)
    return None


def get_cart(session) -> dict[str, int]:
    return _cart_dict(session)


def set_cart(session, data: dict[str, int]) -> None:
    session[CART_SESSION_KEY] = {
        str(k): int(v) for k, v in data.items() if int(v) > 0
    }
    session.modified = True


def add_product(session, product_id: int, quantity: int = 1) -> None:
    cart = _cart_dict(session)
    key = f"p:{product_id}"
    cart[key] = cart.get(key, 0) + max(1, quantity)
    set_cart(session, cart)


def add_variant(session, variant_id: int, quantity: int = 1) -> None:
    cart = _cart_dict(session)
    key = f"v:{variant_id}"
    cart[key] = cart.get(key, 0) + max(1, quantity)
    set_cart(session, cart)


def set_quantity(session, row_key: str, quantity: int) -> None:
    cart = _cart_dict(session)
    parsed = normalize_line_key(row_key)
    if not parsed:
        return
    kind, oid = parsed
    key = f"{kind}:{oid}"
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    set_cart(session, cart)


def remove_row(session, row_key: str) -> None:
    cart = _cart_dict(session)
    parsed = normalize_line_key(row_key)
    if not parsed:
        return
    cart.pop(f"{parsed[0]}:{parsed[1]}", None)
    set_cart(session, cart)


def clear(session) -> None:
    session.pop(CART_SESSION_KEY, None)
    session.pop(COUPON_SESSION_KEY, None)
    session.modified = True


def get_coupon(session):
    """Return the active session Coupon (or None) revalidated against DB state."""
    from commerce.models import Coupon

    code = (session.get(COUPON_SESSION_KEY) or "").strip().upper()
    if not code:
        return None
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None or not coupon.is_currently_active():
        session.pop(COUPON_SESSION_KEY, None)
        session.modified = True
        return None
    return coupon


def set_coupon(session, code: str) -> None:
    session[COUPON_SESSION_KEY] = (code or "").strip().upper()
    session.modified = True


def clear_coupon(session) -> None:
    session.pop(COUPON_SESSION_KEY, None)
    session.modified = True


def iter_cart_lines(session) -> Iterator[CartLine]:
    cart = _cart_dict(session)
    if not cart:
        return
    p_ids: set[int] = set()
    v_ids: set[int] = set()
    rows: list[tuple[str, int, int]] = []
    for raw_key, qty in cart.items():
        parsed = normalize_line_key(raw_key)
        if not parsed or qty <= 0:
            continue
        kind, oid = parsed
        if kind == "p":
            p_ids.add(oid)
        else:
            v_ids.add(oid)
        rows.append((kind, oid, qty))

    products = {
        p.pk: p
        for p in Product.objects.filter(pk__in=p_ids, is_published=True)
        .select_related("category")
        .prefetch_related("gallery_images")
    }
    variants = {
        v.pk: v
        for v in ProductVariant.objects.filter(
            pk__in=v_ids,
            is_active=True,
            product__is_published=True,
        )
        .select_related("product", "product__category")
        .prefetch_related("product__gallery_images")
    }

    for kind, oid, qty in rows:
        if kind == "p":
            p = products.get(oid)
            if not p:
                continue
            if p.has_sellable_variants():
                continue
            if not p.available_to_sell:
                continue
            yield CartLine(product=p, variant=None, quantity=qty)
        else:
            v = variants.get(oid)
            if not v:
                continue
            if not v.available_to_sell:
                continue
            yield CartLine(product=v.product, variant=v, quantity=qty)


def cart_totals(session, tax_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    subtotal, tax, total, _ = cart_totals_with_discount(session, tax_rate)
    return subtotal, tax, total


def cart_totals_with_discount(
    session, tax_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    subtotal = Decimal("0")
    for line in iter_cart_lines(session):
        subtotal += Decimal(line.quantity) * line.unit_price
    subtotal = subtotal.quantize(Decimal("0.01"))
    discount = Decimal("0")
    coupon = get_coupon(session)
    if coupon is not None:
        discount = coupon.compute_discount(subtotal)
    taxable = max(Decimal("0"), subtotal - discount)
    tax = (taxable * (tax_rate / Decimal("100"))).quantize(Decimal("0.01"))
    total = (taxable + tax).quantize(Decimal("0.01"))
    return subtotal, tax, total, discount


def cart_item_count(session) -> int:
    return sum(_cart_dict(session).values())
