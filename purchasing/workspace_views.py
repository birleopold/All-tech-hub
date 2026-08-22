from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View

from catalog.models import Product
from commerce.models import Order, OrderLine
from core.mixins import StaffRequiredMixin
from core.models import ContactMessage
from purchasing import views
from purchasing.models import PurchaseLine, PurchaseOrder, Supplier
from purchasing.replenishment import suggested_reorder_quantity


def replenishment_recommendations(*, limit=12):
    cutoff = timezone.now() - timedelta(days=30)
    products = list(Product.objects.filter(kind=Product.KIND_PHYSICAL, track_inventory=True).filter(
        Q(stock_quantity__lte=F("reorder_level")) | Q(contact_enquiries__created_at__gte=cutoff)
    ).distinct().order_by("stock_quantity", "name")[:100])
    product_ids = [product.pk for product in products]
    sales = {
        row["product_id"]: row["units"]
        for row in OrderLine.objects.filter(product_id__in=product_ids, order__placed_at__gte=cutoff)
        .exclude(order__status=Order.STATUS_CANCELLED).values("product_id").annotate(units=Sum("quantity"))
    }
    enquiries = {
        row["product_id"]: row["count"]
        for row in ContactMessage.objects.filter(product_id__in=product_ids, created_at__gte=cutoff)
        .values("product_id").annotate(count=Count("pk"))
    }
    incoming = {
        row["product_id"]: max(0, row["ordered"] - row["received"])
        for row in PurchaseLine.objects.filter(product_id__in=product_ids, purchase_order__status__in=[PurchaseOrder.STATUS_SENT, PurchaseOrder.STATUS_PARTIAL])
        .values("product_id").annotate(ordered=Sum("quantity"), received=Sum("received_quantity"))
    }
    latest_lines = {}
    for line in PurchaseLine.objects.filter(product_id__in=product_ids).select_related("purchase_order__supplier").order_by("-purchase_order__created_at", "-pk"):
        latest_lines.setdefault(line.product_id, line)
    recommendations = []
    for product in products:
        quantity = suggested_reorder_quantity(on_hand=product.stock_quantity, reorder_level=product.reorder_level,
            recent_sales=sales.get(product.pk, 0), recent_enquiries=enquiries.get(product.pk, 0), pending_inbound=incoming.get(product.pk, 0))
        if quantity <= 0:
            continue
        previous = latest_lines.get(product.pk)
        recommendations.append({"product": product, "recent_sales": sales.get(product.pk, 0), "recent_enquiries": enquiries.get(product.pk, 0),
            "pending_inbound": incoming.get(product.pk, 0), "recommended_quantity": quantity,
            "supplier": previous.purchase_order.supplier if previous else None, "unit_cost": previous.unit_cost if previous else 0,
            "urgent": product.stock_quantity <= 0 or product.stock_quantity < product.reorder_level})
    recommendations.sort(key=lambda row: (not row["urgent"], -row["recent_enquiries"], -row["recent_sales"], row["product"].name))
    return recommendations[:limit]


class PurchasingWorkspaceHomeView(views.PurchasingHomeView):
    """Purchasing overview with actionable order, supplier and demand metrics."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["purchase_stats"] = PurchaseOrder.objects.aggregate(
            total=Count("pk"), draft=Count("pk", filter=Q(status=PurchaseOrder.STATUS_DRAFT)),
            awaiting=Count("pk", filter=Q(status__in=[PurchaseOrder.STATUS_SENT, PurchaseOrder.STATUS_PARTIAL])),
            received=Count("pk", filter=Q(status=PurchaseOrder.STATUS_RECEIVED)))
        context["supplier_count"] = Supplier.objects.count()
        context["replenishment_recommendations"] = replenishment_recommendations()
        return context


class ReplenishmentPurchaseOrderView(StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, kind=Product.KIND_PHYSICAL)
        previous = PurchaseLine.objects.filter(product=product).select_related("purchase_order__supplier").order_by("-purchase_order__created_at", "-pk").first()
        if previous is None:
            messages.warning(request, "Choose a supplier manually for products without purchasing history.")
            return redirect("staff_po_create")
        try:
            quantity = min(10000, max(1, int(request.POST.get("quantity", 1))))
        except (TypeError, ValueError):
            messages.error(request, "Enter a valid reorder quantity.")
            return redirect("staff_purchasing")
        purchase_order = PurchaseOrder.objects.create(supplier=previous.purchase_order.supplier, created_by=request.user,
            notes=f"Demand-based replenishment for {product.name}")
        PurchaseLine.objects.create(purchase_order=purchase_order, product=product, description=product.name, quantity=quantity, unit_cost=previous.unit_cost)
        messages.success(request, f"Draft purchase order {purchase_order.number} created for {quantity} units.")
        return redirect("staff_po_edit", pk=purchase_order.pk)
