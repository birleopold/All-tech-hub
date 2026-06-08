import csv
from datetime import date, timedelta

from django.db.models import F, Sum
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from catalog.models import Product
from catalog.stock_alerts import low_stock_products
from commerce.models import Order, OrderLine
from core.filters import apply_job_filters, apply_ticket_filters
from core.mixins import StaffRequiredMixin
from core.models import SupportTicket
from operations.models import JobCard


def staff_export_orders_csv(request):
    if not request.user.is_staff:
        raise Http404
    qs = Order.objects.select_related("customer").order_by("-placed_at")
    days = request.GET.get("days")
    if days and str(days).isdigit():
        since = timezone.now() - timedelta(days=int(days))
        qs = qs.filter(placed_at__gte=since)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="orders_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "reference",
            "placed_at",
            "status",
            "fulfillment_type",
            "customer_email",
            "total",
        ]
    )
    for order in qs[:5000]:
        writer.writerow(
            [
                order.reference,
                order.placed_at.isoformat(),
                order.status,
                order.fulfillment_type,
                order.customer.email,
                str(order.total),
            ]
        )
    return response


def staff_export_jobs_csv(request):
    if not request.user.is_staff:
        raise Http404
    qs = apply_job_filters(
        JobCard.objects.select_related("customer", "assigned_to"),
        request.GET,
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="job_cards_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "number",
            "title",
            "customer",
            "status",
            "priority",
            "assigned_to",
            "received_on",
            "scheduled_for",
        ]
    )
    for job in qs[:5000]:
        writer.writerow(
            [
                job.number,
                job.title,
                job.customer.name,
                job.status,
                job.priority,
                job.assigned_to.get_username() if job.assigned_to else "",
                job.received_on.isoformat() if job.received_on else "",
                job.scheduled_for.isoformat() if job.scheduled_for else "",
            ]
        )
    return response


def staff_export_tickets_csv(request):
    if not request.user.is_staff:
        raise Http404
    qs = apply_ticket_filters(
        SupportTicket.objects.select_related("customer", "assigned_to"),
        request.GET,
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="support_tickets_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "reference",
            "subject",
            "customer",
            "status",
            "priority",
            "assigned_to",
            "created_at",
            "updated_at",
        ]
    )
    for t in qs[:5000]:
        writer.writerow(
            [
                t.reference,
                t.subject,
                t.customer.name,
                t.status,
                t.priority,
                t.assigned_to.get_username() if t.assigned_to else "",
                t.created_at.isoformat(),
                t.updated_at.isoformat(),
            ]
        )
    return response


def staff_export_low_stock_csv(request):
    if not request.user.is_staff:
        raise Http404
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="low_stock_export.csv"'
    writer = csv.writer(response)
    writer.writerow(["sku", "name", "category", "stock_quantity", "reorder_level"])
    for p in low_stock_products(limit=None):
        writer.writerow(
            [
                p.sku,
                p.name,
                p.category.name,
                p.stock_quantity,
                p.reorder_level,
            ]
        )
    return response


class ReportsHomeView(StaffRequiredMixin, TemplateView):
    template_name = "reports/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start_30 = today - timedelta(days=30)
        start_90 = today - timedelta(days=90)

        base = OrderLine.objects.select_related(
            "product", "product__category", "product_variant", "order"
        )
        base_30 = base.filter(order__placed_at__date__gte=start_30)
        base_90 = base.filter(order__placed_at__date__gte=start_90)

        top_products_30 = (
            base_30.filter(product__kind=Product.KIND_PHYSICAL)
            .values("product_id", "description")
            .annotate(qty=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price")))
            .order_by("-qty")[:10]
        )
        top_services_30 = (
            base_30.filter(product__kind=Product.KIND_SERVICE)
            .values("product_id", "description")
            .annotate(qty=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price")))
            .order_by("-qty")[:10]
        )

        revenue_30 = base_30.aggregate(r=Sum(F("quantity") * F("unit_price")))["r"] or 0
        revenue_90 = base_90.aggregate(r=Sum(F("quantity") * F("unit_price")))["r"] or 0

        ctx.update(
            {
                "today": today,
                "start_30": start_30,
                "start_90": start_90,
                "revenue_30": revenue_30,
                "revenue_90": revenue_90,
                "top_products_30": top_products_30,
                "top_services_30": top_services_30,
                "low_stock_items": low_stock_products(limit=12),
                "low_stock_count": len(low_stock_products(limit=None)),
            }
        )
        return ctx

