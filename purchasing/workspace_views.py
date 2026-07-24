from django.db.models import Count, Q

from purchasing import views
from purchasing.models import PurchaseOrder, Supplier


class PurchasingWorkspaceHomeView(views.PurchasingHomeView):
    """Purchasing overview with actionable order and supplier metrics."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["purchase_stats"] = PurchaseOrder.objects.aggregate(
            total=Count("pk"),
            draft=Count("pk", filter=Q(status=PurchaseOrder.STATUS_DRAFT)),
            awaiting=Count(
                "pk",
                filter=Q(
                    status__in=[PurchaseOrder.STATUS_SENT, PurchaseOrder.STATUS_PARTIAL]
                ),
            ),
            received=Count("pk", filter=Q(status=PurchaseOrder.STATUS_RECEIVED)),
        )
        context["supplier_count"] = Supplier.objects.count()
        return context
