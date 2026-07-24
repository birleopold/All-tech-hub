from django.db.models import Count, Q

from catalog.models import Product
from catalog.stock_alerts import low_stock_products
from inventory import views
from inventory.models import StockTake
from inventory.product_list_view import ProductManageListView


class ProductWorkspaceListView(ProductManageListView):
    """Catalogue register with complete inventory and publication metrics."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product_stats"] = Product.objects.aggregate(
            total=Count("pk"),
            physical=Count("pk", filter=Q(kind=Product.KIND_PHYSICAL)),
            services=Count("pk", filter=Q(kind=Product.KIND_SERVICE)),
            published=Count("pk", filter=Q(is_published=True)),
        )
        context["product_stats"]["low_stock"] = len(low_stock_products(limit=None))
        return context


class StockTakeWorkspaceListView(views.StockTakeListView):
    """Cycle-count register with open and completed count summaries."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stocktake_stats"] = StockTake.objects.aggregate(
            total=Count("pk"),
            open=Count("pk", filter=Q(status=StockTake.STATUS_OPEN)),
            posted=Count("pk", filter=Q(status=StockTake.STATUS_POSTED)),
        )
        return context
