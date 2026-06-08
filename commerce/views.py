import secrets
import uuid
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from billing.models import allocate_document_number
from catalog.models import Product, ProductVariant
from commerce import cart as cart_mod
from commerce.forms import CheckoutForm
from commerce.models import Order, OrderLine
from commerce.stock import InsufficientStock, decrement_line_stock
from core.models import CompanySettings

SESSION_CHECKOUT_TOKEN = "checkout_submit_token"


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
    qty = int(request.POST.get("quantity") or 1)
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
    next_url = request.POST.get("next") or product.get_absolute_url()
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
            cart_mod.set_quantity(request.session, row_key, int(val or 0))
    messages.success(request, "Cart updated.")
    return redirect("cart")


@require_POST
def cart_remove(request, product_id: int):
    """Legacy URL: remove plain product line only."""
    cart_mod.remove_row(request.session, f"p:{product_id}")
    messages.info(request, "Item removed.")
    return redirect("cart")


def checkout_view(request):
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

    checkout_lines = [
        {"line": ln, "qty": ln.quantity, "line_total": ln.unit_price * ln.quantity}
        for ln in lines
    ]

    if request.method == "GET":
        request.session[SESSION_CHECKOUT_TOKEN] = secrets.token_urlsafe(32)
    elif request.method == "POST":
        posted = request.POST.get("checkout_token", "")
        expected = request.session.get(SESSION_CHECKOUT_TOKEN)
        if not expected or posted != expected:
            messages.error(
                request,
                "This checkout step expired or was already submitted. Please review your order and try again.",
            )
            return redirect("checkout")
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    customer = form.save_customer()
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
                        customer_note=form.cleaned_data.get("customer_note") or "",
                        subtotal=subtotal,
                        tax_rate=tax_rate,
                        tax_amount=tax,
                        discount_amount=discount,
                        coupon=coupon,
                        coupon_code_applied=coupon.code if coupon else "",
                        total=total,
                    )
                    if coupon is not None:
                        from django.db.models import F as _F

                        type(coupon).objects.filter(pk=coupon.pk).update(
                            times_used=_F("times_used") + 1
                        )
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
                        )
                    cart_mod.clear(request.session)
            except InsufficientStock as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            request.session.pop(SESSION_CHECKOUT_TOKEN, None)
            messages.success(
                request,
                f"Order placed — reference {order.reference}. We will contact you to confirm payment and delivery.",
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
        form = CheckoutForm(initial=initial)

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
            "tax_amount": tax,
            "discount": discount,
            "total": total,
            "coupon": coupon,
        },
    )


def order_detail(request, reference: str, view_key: uuid.UUID):
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        reference=reference,
        view_key=view_key,
    )
    return render(request, "commerce/order_detail.html", {"order": order})
