from urllib.parse import urlsplit

from django.urls import resolve

from catalog.models import Product, ProductVariant
from commerce import cart as cart_mod
from commerce.models import Order
from growth.services import (
    analytics_item,
    mark_order_growth_attribution,
    queue_analytics_event,
    touch_saved_cart,
)


class GrowthCommerceMiddleware:
    """Observe successful shop actions without changing checkout transaction logic."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        name = getattr(match, "url_name", "") or ""

        if request.method == "POST" and response.status_code in (301, 302, 303):
            if name == "cart_add":
                self._record_successful_cart_add(request, match)
            elif name in {"cart_update", "cart_remove"}:
                touch_saved_cart(request)
            elif name == "checkout":
                self._record_successful_checkout(request, response)
        return response

    @staticmethod
    def _record_successful_cart_add(request, match):
        product_id = (match.kwargs or {}).get("product_id") if match else None
        product = Product.objects.select_related("category").filter(
            pk=product_id,
            is_published=True,
        ).first()
        if not product:
            return

        current_cart = cart_mod.get_cart(request.session)
        variant = None
        row_key = f"p:{product.pk}"
        if product.has_sellable_variants():
            variant_id = request.POST.get("variant_id")
            if not variant_id or not str(variant_id).isdigit():
                return
            variant = ProductVariant.objects.select_related(
                "product",
                "product__category",
            ).filter(
                pk=int(variant_id),
                product=product,
                is_active=True,
            ).first()
            if not variant or not variant.available_to_sell:
                return
            row_key = f"v:{variant.pk}"
        elif not product.available_to_sell:
            return

        if row_key not in current_cart:
            return
        try:
            quantity = max(1, int(request.POST.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        item = analytics_item(
            product,
            variant=variant,
            quantity=quantity,
        )
        price = float(variant.price if variant else product.price)
        queue_analytics_event(
            request,
            "add_to_cart",
            {
                "currency": "UGX",
                "value": price * quantity,
                "items": [item],
            },
        )
        touch_saved_cart(request)

    @staticmethod
    def _record_successful_checkout(request, response):
        location = response.get("Location", "")
        if not location:
            return
        try:
            target = resolve(urlsplit(location).path)
        except Exception:
            return
        if target.url_name != "order_detail":
            return
        reference = target.kwargs.get("reference")
        order = Order.objects.filter(reference=reference).first()
        if order:
            mark_order_growth_attribution(request, order)
