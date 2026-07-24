from django.utils import timezone

from catalog.models import Product
from catalog.stock_alerts import low_stock_products
from inventory import views
from inventory.models import StockAdjustment


class StaffInventoryHomeView(views.InventoryHomeView):
    """Inventory overview with catalogue and stock-operation metrics."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_queryset = Product.objects.filter(kind=Product.KIND_PHYSICAL)
        context["inventory_stats"] = {
            "products": product_queryset.count(),
            "published": product_queryset.filter(is_published=True).count(),
            "tracked": product_queryset.filter(track_inventory=True).count(),
            "low_stock": len(low_stock_products(limit=None)),
            "adjustments_today": StockAdjustment.objects.filter(
                created_at__date=timezone.localdate()
            ).count(),
        }
        return context
