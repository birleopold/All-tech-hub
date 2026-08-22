import secrets
import uuid
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from billing.models import allocate_document_number
from catalog.models import Product, ProductVariant
from commerce import cart as cart_mod
from commerce.customer_messages import send_order_confirmation_by_id
from commerce.forms import CheckoutForm
from commerce.models import Order, OrderLine
from commerce.recommendations import (
    recommended_products_for_lines,
    recommended_products_for_order,
)
from commerce.stock import InsufficientStock, decrement_line_stock
from core.models import CompanySettings
from marketing.attribution import SESSION_ATTRIBUTION_KEY, order_attribution
from reliability.services import create_order_reservation, order_for_idempotency_key

SESSION_CHECKOUT_TOKEN = "checkout_submit_token"


class CouponUnavailable(Exception):
    pass


def _safe_next_url(request, candidate: str | None, fallback: str) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def _positive_int(raw, default: int = 1, maximum: int = 999) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _qty_field_to_row_key(field_name: str) -> str | None:
    if not field_name.startswith("qty_"):
        return None
    inner = field_name[4:]
    if inner.startswith("p_") and inner[2:].isdigit():
        return f"p:{inner[2:]}"
    if inner.startswith("v_") and inner[2:].isdigit():
        return f"v:{inner[2:]}"
    return None


def cart_view(request):
    lines = list(cart_mod.iter_cart_lines(request.session))
    company = CompanySettings.load()
    tax_rate = company.default_tax_rate
    subtotal, tax, total, discount = cart_mod.cart_totals_with_discount(
        request.session, tax_rate
    )
    coupon = cart_mod.get_coupon(request.session)
    return render(
        request,
        "commerce/cart.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "tax_rate": tax_rate,
            "tax_amount": tax,
            "discount": discount,
            "total": total,
            "coupon": coupon,
            "recommended_products": recommended_products_for_lines(lines),
            "recommendation_title": "Useful additions for this order",
        },
    )


@require_POST
def cart_apply_coupon(request):
    code = (request.POST.get("code") or "").strip().upper()
    if not code:
        messages.error(request, "Enter a discount code.")
        return redirect("cart")
    from commerce.models import Coupon

    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None or not coupon.is_currently_active():
        cart_mod.clear_coupon(request.session)
        messages.error(request, "That code is invalid or expired.")
        return redirect("cart")
    company = CompanySettings.load()
    subtotal, _tax, _total = cart_mod.cart_totals(request.session, company.default_tax_rate)
    if subtotal < coupon.min_subtotal:
        messages.error(
            request,
            f"Add {company.currency_code} {coupon.min_subtotal - subtotal:.2f} more to use this code.",
        )
        return redirect("cart")
    cart_mod.set_coupon(request.session, coupon.code)
    messages.success(request, f"Code “{coupon.code}” applied.")
    return redirect("cart")


@require_POST
def cart_remove_coupon(request):
    cart_mod.clear_coupon(request.session)
    messages.info(request, "Discount code removed.")
    return redirect("cart")


@require_POST
def cart_add(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id, is_published=True)
    qty = _positive_int(request.POST.get("quantity"), default=1)
    variant_id = request.POST.get("variant_id")

    if product.has_sellable_variants():
        if not variant_id or not str(variant_id).isdigit():
            messages.error(request, "Choose an option before adding to cart.")
            return redirect("product_detail", slug=product.slug)
        variant = get_object_or_404(
            ProductVariant,
            pk=int(variant_id),
            product=product,
            is_active=True,
        )
        if not variant.available_to_sell:
            messages.error(request, "That option is not available.")
            return redirect("product_detail", slug=product.slug)
        cart_mod.add_variant(request.session, variant.pk, qty)
        messages.success(
            request,
            f"Added “{product.name} ({variant.name})” to cart.",
        )
    else:
        if not product.available_to_sell:
            messages.error(request, "This item is not available.")
            return redirect("product_detail", slug=product.slug)
        cart_mod.add_product(request.session, product.pk, qty)
        messages.success(request, f"Added “{product.name}” to cart.")
    next_url = _safe_next_url(
        request, request.POST.get("next"), product.get_absolute_url()
    )
    return redirect(next_url)


@require_POST
def cart_update(request):
    remove_key = request.POST.get("remove")
    if remove_key:
        cart_mod.remove_row(request.session, remove_key)
        messages.info(request, "Item removed.")
        return redirect("cart")
    for key, val in request.POST.items():
        row_key = _qty_field_to_row_key(key)
        if row_key:
            try:
                quantity = int(val or 0)
            except (TypeError, ValueError):
                messages.error(request, "Quantities must be whole numbers.")
                return redirect("cart")
            cart_mod.set_quantity(request.session, row_key, min(quantity, 999))
    messages.success(request, "Cart updated.")
    return redirect("cart")


@require_POST
def cart_remove(request, product_id: int):
    """Legacy URL: remove plain product line only."""
    cart_mod.remove_row(request.session, f"p:{product_id}")
    messages.info(request, "Item removed.")
    return redirect("cart")


def checkout_view(request):
    posted = ""
    if request.method == "POST":
        posted = (request.POST.get("checkout_token") or "").strip()
        existing_order = order_for_idempotency_key(posted)
        if existing_order is not None:
            cart_mod.clear(request.session)
            request.session.pop(SESSION_CHECKOUT_TOKEN, None)
            request.session.pop(SESSION_ATTRIBUTION_KEY, None)
            messages.info(
                request,
                f"Order {existing_order.reference} was already received. No duplicate order was created.",
            )
            return redirect(
                "order_detail",
                reference=existing_order.reference,
                view_key=existing_order.view_key,
            )

    lines = list(cart_mod.iter_cart_lines(request.session))
    if not lines:
        messages.warning(request, "Your cart is empty.")
        return redirect("product_list")

    company = CompanySettings.load()
    tax_rate = company.default_tax_rate
    subtotal, tax, total, discount = cart_mod.cart_totals_with_discount(
        request.session, tax_rate
    )
    coupon = cart_mod.get_coupon(request.session)

    delivery_fee = Decimal("0.00")
    delivery_tax = Decimal("0.00")

    checkout_lines = [
        {"line": ln, "qty": ln.quantity, "line_total": ln.unit_price * ln.quantity}
        for ln in lines
    ]

    if request.method == "GET":
        request.session[SESSION_CHECKOUT_TOKEN] = secrets.token_urlsafe(32)
    elif request.method == "POST":
        expected = request.session.get(SESSION_CHECKOUT_TOKEN)
        if not expected or posted != expected:
            messages.error(
                request,
                "This checkout step expired or was already submitted. Please review your order and try again.",
            )
            return redirect("checkout")
        form = CheckoutForm(request.POST, request_user=request.user)
        if form.is_valid():
            reused_order = False
            try:
                with transaction.atomic():
                    locked_coupon = None
                    if coupon is not None:
                        from commerce.models import Coupon

                        locked_coupon = Coupon.objects.select_for_update().get(
                            pk=coupon.pk
                        )
                        if not locked_coupon.is_currently_active():
                            raise CouponUnavailable(
                                "That discount code has reached its usage limit or expired."
                            )
                    customer = form.save_customer()
                    selected_zone = form.cleaned_data.get("delivery_zone")
                    delivery_fee = form.delivery_fee
                    delivery_tax = (
                        delivery_fee * tax_rate / Decimal("100")
                    ).quantize(Decimal("0.01"))
                    ref = allocate_document_number("ORD")
                    order = Order.objects.create(
                        reference=ref,
                        customer=customer,
                        user=request.user if request.user.is_authenticated else None,
                        contact_name=form.cleaned_data["name"],
                        contact_email=form.cleaned_data["email"],
                        contact_phone=form.cleaned_data.get("phone") or "",
                        billing_summary=form.cleaned_data["billing_address"],
                        shipping_summary=form.cleaned_data.get("shipping_address")
                        or form.cleaned_data["billing_address"],
                        fulfillment_type=form.cleaned_data["fulfillment_type"],
                        delivery_zone_name=selected_zone.name if selected_zone else "",
                        delivery_fee=delivery_fee,
                        customer_note=form.cleaned_data.get("customer_note") or "",
                        subtotal=subtotal,
                        tax_rate=tax_rate,
                        tax_amount=tax + delivery_tax,
                        discount_amount=discount,
                        coupon=locked_coupon,
                        coupon_code_applied=locked_coupon.code if locked_coupon else "",
                        total=total + delivery_fee + delivery_tax,
                        **order_attribution(request.session),
                    )
                    if locked_coupon is not None:
                        from django.db.models import F as _F

                        type(locked_coupon).objects.filter(
                            pk=locked_coupon.pk
                        ).update(times_used=_F("times_used") + 1)
                    for ln in lines:
                        desc = ln.label
                        sku = (
                            (ln.variant.sku if ln.variant and ln.variant.sku else "")
                            or ln.product.sku
                        )
                        OrderLine.objects.create(
                            order=order,
                            product=ln.product,
                            product_variant=ln.variant,
                            description=desc[:300],
                            sku=sku[:64],
                            quantity=ln.quantity,
                            unit_price=ln.unit_price,
                        )
                        decrement_line_stock(
                            product=ln.product,
                            variant=ln.variant,
                            qty=ln.quantity,
                            reference=order.reference,
                        )
                    create_order_reservation(
                        order,
                        posted,
                        actor=request.user if request.user.is_authenticated else None,
                    )
                    order_id = order.pk
                    transaction.on_commit(
                        lambda: send_order_confirmation_by_id(order_id)
                    )
            except InsufficientStock as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            except CouponUnavailable as exc:
                cart_mod.clear_coupon(request.session)
                messages.error(request, str(exc))
                return redirect("cart")
            except (IntegrityError, ValidationError):
                order = order_for_idempotency_key(posted)
                if order is None:
                    raise
                reused_order = True

            cart_mod.clear(request.session)
            request.session.pop(SESSION_CHECKOUT_TOKEN, None)
            request.session.pop(SESSION_ATTRIBUTION_KEY, None)
            if reused_order:
                messages.info(
                    request,
                    f"Order {order.reference} was already received. No duplicate order was created.",
                )
            else:
                messages.success(
                    request,
                    f"Order placed — reference {order.reference}. Stock is reserved while payment and delivery are confirmed.",
                )
            return redirect(
                "order_detail",
                reference=order.reference,
                view_key=order.view_key,
            )
    if request.method != "POST":
        initial = {}
        if request.user.is_authenticated:
            prof = getattr(request.user, "customer_profile", None)
            if prof is not None:
                initial = {
                    "name": prof.name,
                    "email": prof.email,
                    "phone": prof.phone,
                    "company_name": prof.company_name,
                }
        form = CheckoutForm(initial=initial, request_user=request.user)

    return render(
        request,
        "commerce/checkout.html",
        {
            "form": form,
            "checkout_token": request.session.get(SESSION_CHECKOUT_TOKEN, ""),
            "lines": lines,
            "checkout_lines": checkout_lines,
            "subtotal": subtotal,
            "tax_rate": tax_rate,
            "tax_amount": tax + delivery_tax,
            "discount": discount,
            "delivery_fee": delivery_fee,
            "delivery_zones_available": form.delivery_zones_available,
            "delivery_zone_rates": {
                str(zone.pk): str(zone.fee_from or Decimal("0.00"))
                for zone in form.fields["delivery_zone"].queryset
            },
            "total": total + delivery_fee + delivery_tax,
            "coupon": coupon,
        },
    )


def order_detail(request, reference: str, view_key: uuid.UUID):
    order = get_object_or_404(
        Order.objects.select_related("customer", "stock_reservation").prefetch_related(
            "lines__product__category",
            "lines__product_variant",
            "status_events",
        ),
        reference=reference,
        view_key=view_key,
    )
    return render(
        request,
        "commerce/order_detail.html",
        {
            "order": order,
            "recommended_products": recommended_products_for_order(order),
            "recommendation_title": "You may also need",
        },
    )
