"""Read-only, source-separated online orders and document reconciliation."""
from datetime import timedelta

from django.db.models import Count
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import CommercialDocument, CommercialLine
from commerce.models import Order, OrderLine
from core.mixins import StaffRequiredMixin


class FinancialReconciliationView(PermissionRequiredMixin, StaffRequiredMixin, TemplateView):
    permission_required = 'billing.view_document_margin'
    raise_exception = True
    template_name = "reports/financial_reconciliation.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        days = self.request.GET.get("days", "30")
        days = int(days) if days in {"7", "30", "90"} else 30
        since = timezone.now() - timedelta(days=days)
        start_day = timezone.localdate(since)
        online_orders = Order.objects.filter(placed_at__gte=since).exclude(
            status=Order.STATUS_CANCELLED
        )
        lines = OrderLine.objects.filter(order__in=online_orders)
        docs = CommercialDocument.objects.filter(
            issue_date__gte=start_day,
            status__in=(
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PARTIALLY_PAID,
                CommercialDocument.STATUS_PAID,
            ),
        ).exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
        document_lines = CommercialLine.objects.filter(document__in=docs)
        ctx.update({
            "days": days,
            "online_orders": online_orders.count(),
            "online_lines": lines.count(),
            "online_line_total": sum(
                (line.quantity * line.unit_price for line in lines.iterator(chunk_size=200)), 0
            ),
            "document_count": docs.count(),
            "document_gross": sum((doc.total for doc in docs.iterator(chunk_size=200)), 0),
            "document_lines": document_lines.count(),
            "documents_without_lines": docs.annotate(
                line_count=Count("lines")
            ).filter(line_count=0).count(),
            "largest_documents": docs.order_by("-total", "-pk")[:15],
        })
        return ctx
