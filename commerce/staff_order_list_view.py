from django.db.models import Count, Q
from django.views.generic import ListView

from commerce.models import Order
from core.mixins import StaffRequiredMixin


class StaffOrderListView(StaffRequiredMixin, ListView):
    """Searchable staff order queue with operational summary metrics."""

    model = Order
    template_name = "commerce/staff_order_list.html"
    context_object_name = "orders"
    paginate_by = 25

    def get_queryset(self):
        queryset = Order.objects.select_related("customer").order_by("-placed_at")
        status = (self.request.GET.get("status") or "").strip()
        queue = (self.request.GET.get("queue") or "").strip()
        query = (self.request.GET.get("q") or "").strip()
        fulfillment = (self.request.GET.get("fulfillment") or "").strip()
        terminal_statuses = [
            Order.STATUS_CANCELLED,
            Order.STATUS_DELIVERED,
            Order.STATUS_FULFILLED,
        ]

        if status in dict(Order.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        elif queue == "active":
            queryset = queryset.exclude(status__in=terminal_statuses)
        elif queue == "completed":
            queryset = queryset.filter(
                status__in=[Order.STATUS_DELIVERED, Order.STATUS_FULFILLED]
            )
        if fulfillment in {Order.FULFILLMENT_DELIVERY, Order.FULFILLMENT_PICKUP}:
            queryset = queryset.filter(fulfillment_type=fulfillment)
        if query:
            queryset = queryset.filter(
                Q(reference__icontains=query)
                | Q(customer__name__icontains=query)
                | Q(customer__email__icontains=query)
                | Q(customer__phone__icontains=query)
                | Q(contact_name__icontains=query)
                | Q(contact_email__icontains=query)
                | Q(contact_phone__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        terminal_statuses = [
            Order.STATUS_CANCELLED,
            Order.STATUS_DELIVERED,
            Order.STATUS_FULFILLED,
        ]
        stats = Order.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=~Q(status__in=terminal_statuses)),
            dispatched=Count("pk", filter=Q(status=Order.STATUS_DISPATCHED)),
            completed=Count(
                "pk",
                filter=Q(status__in=[Order.STATUS_DELIVERED, Order.STATUS_FULFILLED]),
            ),
        )
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context.update(
            {
                "order_status_choices": Order.STATUS_CHOICES,
                "selected_status": (self.request.GET.get("status") or "").strip(),
                "selected_queue": (self.request.GET.get("queue") or "").strip(),
                "selected_fulfillment": (
                    (self.request.GET.get("fulfillment") or "").strip()
                ),
                "q": (self.request.GET.get("q") or "").strip(),
                "order_stats": stats,
                "querystring": query_params.urlencode(),
            }
        )
        return context
