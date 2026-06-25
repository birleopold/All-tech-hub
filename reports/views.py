import csv
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import (
    AccountPayment,
    CommercialDocument,
    CommercialLine,
    DocumentPayment,
    DocumentSequence,
)
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
    qs = Order.objects.select_related("customer", "shipment").order_by("-placed_at")
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
            "carrier",
            "tracking_number",
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
                getattr(getattr(order, "shipment", None), "carrier", ""),
                getattr(getattr(order, "shipment", None), "tracking_number", ""),
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


def staff_export_documents_csv(request):
    if not request.user.is_staff:
        raise Http404
    documents = CommercialDocument.objects.select_related(
        "customer", "salesperson"
    ).order_by("-issue_date", "-id")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="commercial_documents.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "number",
            "type",
            "status",
            "customer",
            "issue_date",
            "due_date",
            "subtotal",
            "discount",
            "tax",
            "withholding",
            "total",
            "paid",
            "balance",
            "salesperson",
        ]
    )
    for document in documents[:5000]:
        writer.writerow(
            [
                document.number,
                document.doc_type,
                document.status,
                document.display_customer_name,
                document.issue_date,
                document.due_date or "",
                document.subtotal,
                document.discount_amount,
                document.tax_amount,
                document.withholding_tax_amount,
                document.total,
                document.amount_paid,
                document.balance_due,
                document.salesperson.get_username() if document.salesperson else "",
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
        ).exclude(order__status=Order.STATUS_CANCELLED)
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
                "invoice_aging": self._invoice_aging(today),
                "fulfillment_counts": [
                    {
                        "label": label,
                        "count": Order.objects.filter(status=value).count(),
                    }
                    for value, label in Order.STATUS_CHOICES
                ],
                "unfulfilled_orders": Order.objects.exclude(
                    status__in=[
                        Order.STATUS_DELIVERED,
                        Order.STATUS_FULFILLED,
                        Order.STATUS_CANCELLED,
                    ]
                ).count(),
                "document_sales_today": sum(
                    (
                        document.total
                        for document in CommercialDocument.objects.filter(
                            issue_date=today,
                            status__in=[
                                CommercialDocument.STATUS_ISSUED,
                                CommercialDocument.STATUS_PARTIALLY_PAID,
                                CommercialDocument.STATUS_PAID,
                            ],
                        ).exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
                    ),
                    0,
                ),
                "cash_received_today": sum(
                    DocumentPayment.objects.filter(
                        recorded_at__date=today,
                        method=DocumentPayment.METHOD_CASH,
                    ).values_list("amount", flat=True),
                    0,
                ),
                "external_item_margin_30": self._external_item_margin(start_30),
                "document_sequence_gaps": self._document_sequence_gaps(today.year),
                "document_margin_30": self._document_margin(start_30),
                "discount_leakage_30": self._discount_leakage(start_30),
                "top_margin_lines_30": self._top_margin_lines(start_30),
                "sla_summary": self._sla_summary(start_90),
                "job_status_aging": self._job_status_aging(),
                "stock_velocity_30": self._stock_velocity(start_30),
                "payment_exceptions": self._payment_exceptions(),
                "top_customers_90": self._top_customers(start_90),
            }
        )
        return ctx

    @staticmethod
    def _invoice_aging(today):
        buckets = [
            {"label": "Current", "minimum": None, "maximum": 0, "amount": 0},
            {"label": "1–30 days", "minimum": 1, "maximum": 30, "amount": 0},
            {"label": "31–60 days", "minimum": 31, "maximum": 60, "amount": 0},
            {"label": "61+ days", "minimum": 61, "maximum": None, "amount": 0},
        ]
        invoices = CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_INVOICE
        ).exclude(
            status__in=[
                CommercialDocument.STATUS_PAID,
                CommercialDocument.STATUS_CANCELLED,
            ]
        )
        for invoice in invoices:
            overdue = (today - (invoice.due_date or invoice.issue_date)).days
            for bucket in buckets:
                lower_ok = bucket["minimum"] is None or overdue >= bucket["minimum"]
                upper_ok = bucket["maximum"] is None or overdue <= bucket["maximum"]
                if lower_ok and upper_ok:
                    bucket["amount"] += invoice.balance_due
                    break
        return buckets

    @staticmethod
    def _external_item_margin(start_date):
        lines = CommercialLine.objects.filter(
            document__issue_date__gte=start_date,
            source_type__in=[
                CommercialLine.SOURCE_EXTERNAL,
                CommercialLine.SOURCE_CONSIGNMENT,
            ],
        ).select_related("document")
        revenue = sum((line.net_subtotal for line in lines), 0)
        cost = sum((line.total_cost for line in lines), 0)
        return {"revenue": revenue, "cost": cost, "profit": revenue - cost}

    @staticmethod
    def _document_sequence_gaps(year):
        gaps = []
        for sequence in DocumentSequence.objects.filter(year=year):
            actual = CommercialDocument.objects.filter(
                number__startswith=f"{sequence.key}-{year}-"
            ).count()
            if actual < sequence.last_value:
                gaps.append(
                    {
                        "prefix": sequence.key,
                        "allocated": sequence.last_value,
                        "documents": actual,
                        "gap": sequence.last_value - actual,
                    }
                )
        return gaps

    @staticmethod
    def _document_margin(start_date):
        docs = CommercialDocument.objects.filter(
            issue_date__gte=start_date,
            status__in=[
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PARTIALLY_PAID,
                CommercialDocument.STATUS_PAID,
            ],
        ).exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE).prefetch_related("lines")
        revenue = sum((doc.subtotal - doc.discount_amount for doc in docs), Decimal("0"))
        cost = sum((doc.total_cost for doc in docs), Decimal("0"))
        profit = revenue - cost
        margin = Decimal("0")
        if revenue > 0:
            margin = (profit / revenue * Decimal("100")).quantize(Decimal("0.01"))
        return {
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "margin": margin,
        }

    @staticmethod
    def _discount_leakage(start_date):
        docs = CommercialDocument.objects.filter(
            issue_date__gte=start_date,
            status__in=[
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PARTIALLY_PAID,
                CommercialDocument.STATUS_PAID,
            ],
        ).exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
        total_discount = sum(
            (doc.discount_amount + doc.line_discount_amount for doc in docs),
            Decimal("0"),
        )
        gross = sum((doc.subtotal + doc.line_discount_amount for doc in docs), Decimal("0"))
        rate = Decimal("0")
        if gross > 0:
            rate = (total_discount / gross * Decimal("100")).quantize(Decimal("0.01"))
        return {"amount": total_discount, "rate": rate}

    @staticmethod
    def _top_margin_lines(start_date):
        rows = []
        lines = CommercialLine.objects.filter(
            document__issue_date__gte=start_date,
            document__status__in=[
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PARTIALLY_PAID,
                CommercialDocument.STATUS_PAID,
            ],
        ).exclude(document__doc_type=CommercialDocument.TYPE_CREDIT_NOTE).select_related(
            "document", "product", "product__category"
        )
        for line in lines:
            rows.append(
                {
                    "description": line.description,
                    "document": line.document.number,
                    "revenue": line.net_subtotal,
                    "cost": line.total_cost,
                    "profit": line.gross_profit,
                    "margin": (
                        (line.gross_profit / line.net_subtotal * Decimal("100")).quantize(
                            Decimal("0.01")
                        )
                        if line.net_subtotal > 0
                        else Decimal("0")
                    ),
                }
            )
        rows.sort(key=lambda row: row["profit"], reverse=True)
        return rows[:10]

    @staticmethod
    def _sla_summary(start_date):
        open_jobs = JobCard.objects.exclude(
            status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
        )
        overdue_jobs = [job for job in open_jobs if job.is_overdue]
        completed = JobCard.objects.filter(
            status=JobCard.STATUS_COMPLETED,
            closed_on__date__gte=start_date,
        )
        cycle_days = []
        for job in completed:
            if job.closed_on and job.received_on:
                cycle_days.append((job.closed_on - job.received_on).total_seconds() / 86400)
        avg_cycle = sum(cycle_days) / len(cycle_days) if cycle_days else None
        open_tickets = SupportTicket.objects.exclude(
            status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED]
        )
        overdue_tickets = [ticket for ticket in open_tickets if ticket.is_overdue]
        return {
            "open_jobs": open_jobs.count(),
            "overdue_jobs": len(overdue_jobs),
            "completed_jobs": completed.count(),
            "avg_cycle_days": round(avg_cycle, 1) if avg_cycle is not None else None,
            "open_tickets": open_tickets.count(),
            "overdue_tickets": len(overdue_tickets),
        }

    @staticmethod
    def _job_status_aging():
        rows = []
        for value, label in JobCard.STATUS_CHOICES:
            jobs = JobCard.objects.filter(status=value)
            if value in (JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED):
                continue
            count = jobs.count()
            days = [job.days_in_current_status for job in jobs]
            avg_days = round(sum(days) / len(days), 1) if days else 0
            rows.append({"status": label, "count": count, "avg_days": avg_days})
        return rows

    @staticmethod
    def _stock_velocity(start_date):
        rows = []
        sales = (
            OrderLine.objects.filter(order__placed_at__date__gte=start_date)
            .exclude(order__status=Order.STATUS_CANCELLED)
            .values("product_id", "product_variant_id", "description")
            .annotate(qty=Sum("quantity"), orders=Count("order_id", distinct=True))
            .order_by("-qty")[:15]
        )
        product_ids = [row["product_id"] for row in sales if row["product_id"]]
        products = {
            product.pk: product
            for product in Product.objects.filter(pk__in=product_ids).prefetch_related(
                "variants"
            )
        }
        for row in sales:
            product = products.get(row["product_id"])
            on_hand = None
            if product:
                if row["product_variant_id"]:
                    variant = product.variants.filter(pk=row["product_variant_id"]).first()
                    on_hand = int(variant.stock_quantity) if variant else None
                else:
                    on_hand = int(product.stock_quantity)
            qty = int(row["qty"] or 0)
            days_cover = None
            if on_hand is not None and qty > 0:
                days_cover = round(on_hand / (qty / 30), 1)
            rows.append(
                {
                    "description": row["description"],
                    "qty": qty,
                    "orders": row["orders"],
                    "on_hand": on_hand,
                    "days_cover": days_cover,
                }
            )
        return rows

    @staticmethod
    def _payment_exceptions():
        unreconciled = DocumentPayment.objects.filter(reconciled=False)
        unallocated = [
            payment
            for payment in AccountPayment.objects.select_related("customer")
            if payment.unallocated_amount > 0
        ]
        overdue_docs = [
            doc
            for doc in CommercialDocument.objects.filter(
                doc_type=CommercialDocument.TYPE_INVOICE,
                due_date__lt=timezone.localdate(),
            ).exclude(
                status__in=[
                    CommercialDocument.STATUS_PAID,
                    CommercialDocument.STATUS_CANCELLED,
                ]
            )
            if doc.balance_due > 0
        ]
        return {
            "unreconciled_count": unreconciled.count(),
            "unreconciled_amount": sum(
                unreconciled.values_list("amount", flat=True), Decimal("0")
            ),
            "unallocated_count": len(unallocated),
            "unallocated_amount": sum(
                (payment.unallocated_amount for payment in unallocated), Decimal("0")
            ),
            "overdue_invoice_count": len(overdue_docs),
            "overdue_invoice_amount": sum(
                (doc.balance_due for doc in overdue_docs), Decimal("0")
            ),
        }

    @staticmethod
    def _top_customers(start_date):
        docs = (
            CommercialDocument.objects.filter(
                issue_date__gte=start_date,
                status__in=[
                    CommercialDocument.STATUS_ISSUED,
                    CommercialDocument.STATUS_PARTIALLY_PAID,
                    CommercialDocument.STATUS_PAID,
                ],
            )
            .exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
            .select_related("customer")
        )
        rows = {}
        for doc in docs:
            key = doc.customer_id or f"walkin:{doc.display_customer_name}"
            row = rows.setdefault(
                key,
                {
                    "customer": doc.display_customer_name,
                    "documents": 0,
                    "revenue": Decimal("0"),
                    "balance": Decimal("0"),
                },
            )
            row["documents"] += 1
            row["revenue"] += doc.total
            row["balance"] += doc.balance_due
        ordered = sorted(rows.values(), key=lambda row: row["revenue"], reverse=True)
        return ordered[:10]

