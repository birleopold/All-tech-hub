import csv
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import Http404, HttpResponse
from django.utils import timezone

from billing.financials import (
    document_business_cost,
    document_customer_total,
    document_owner_payout,
    document_recognized_income,
    line_business_cost,
    line_owner_payout,
    line_profit,
    line_recognized_income,
    line_margin_percent,
    queryset_financial_summary,
)
from billing.models import CommercialDocument, CommercialLine
from billing.partner_payables import partner_payables_summary
from operations.models import JobExpense
from reports import views

RECOGNIZED_DOCUMENT_STATUSES = (
    CommercialDocument.STATUS_ISSUED,
    CommercialDocument.STATUS_PARTIALLY_PAID,
    CommercialDocument.STATUS_PAID,
)


def is_recognized_document(document):
    return (
        document.status in RECOGNIZED_DOCUMENT_STATUSES
        and document.doc_type != CommercialDocument.TYPE_CREDIT_NOTE
    )


def recognized_documents(start_date=None, end_date=None):
    qs = (
        CommercialDocument.objects.filter(status__in=RECOGNIZED_DOCUMENT_STATUSES)
        .exclude(doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
        .select_related("customer", "salesperson")
        .prefetch_related("lines")
    )
    if start_date is not None:
        qs = qs.filter(issue_date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(issue_date__lte=end_date)
    return qs


def payable_lines(start_date=None, end_date=None):
    qs = (
        CommercialLine.objects.filter(
            document__status__in=RECOGNIZED_DOCUMENT_STATUSES,
        )
        .exclude(document__doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
        .select_related("document")
    )
    if start_date is not None:
        qs = qs.filter(document__issue_date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(document__issue_date__lte=end_date)
    return [line for line in qs if line_owner_payout(line) > 0]


class ReportsHomeView(views.ReportsHomeView):
    def get_template_names(self):
        if not self.request.user.has_perm("billing.view_document_margin"):
            return ["reports/operations_home.html"]
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_view_financial_reports"] = self.request.user.has_perm(
            "billing.view_document_margin"
        )
        ctx["can_view_jobs"] = self.request.user.has_perm(
            "operations.view_jobcard"
        )
        ctx["can_view_orders"] = self.request.user.has_perm(
            "commerce.view_order"
        )
        ctx["can_view_stock"] = self.request.user.has_perm(
            "catalog.view_product"
        )
        if not ctx["can_view_financial_reports"]:
            # Never pass cost and profitability details to the operational
            # staff template (not even through context variables).
            for key in (
                "document_margin_30", "external_item_margin_30",
                "top_margin_lines_30", "partner_payables_30",
                "partner_payables_total_30", "top_customers_90",
                "payment_exceptions", "invoice_aging",
                "document_sales_today", "cash_received_today",
                "discount_leakage_30", "document_sequence_gaps",
            ):
                ctx.pop(key, None)
            return ctx
        today = timezone.localdate()
        start_30 = today - timedelta(days=30)
        today_documents = recognized_documents(start_date=today, end_date=today)
        today_summary = queryset_financial_summary(today_documents)
        partner_payables_30 = partner_payables_summary(payable_lines(start_date=start_30))
        ctx["document_sales_today"] = today_summary["recognized_income"]
        ctx["document_customer_total_today"] = today_summary["customer_total"]
        ctx["document_owner_payout_today"] = today_summary["owner_payout"]
        ctx["can_view_job_expenses"] = self.request.user.has_perm(
            "operations.view_jobexpense"
        )
        if ctx["can_view_job_expenses"]:
            recorded_costs = JobExpense.objects.filter(
                recorded_at__date__gte=start_30
            )
            ctx["recorded_job_expenses_30"] = recorded_costs.aggregate(
                total=Sum("amount"), entries=Count("pk")
            )
            ctx["recorded_job_expenses_30"]["total"] = (
                ctx["recorded_job_expenses_30"]["total"] or Decimal("0")
            )
            ctx["top_recorded_job_costs_30"] = (
                recorded_costs.values("job_id", "job__number", "job__title")
                .annotate(amount=Sum("amount"), entries=Count("pk"))
                .order_by("-amount", "job__number")[:10]
            )
        ctx["partner_payables_30"] = partner_payables_30[:10]
        ctx["partner_payables_total_30"] = sum(
            (row["amount_due"] for row in partner_payables_30), Decimal("0.00")
        )
        return ctx

    @staticmethod
    def _external_item_margin(start_date):
        lines = (
            CommercialLine.objects.filter(
                document__issue_date__gte=start_date,
                document__status__in=RECOGNIZED_DOCUMENT_STATUSES,
                source_type__in=[
                    CommercialLine.SOURCE_EXTERNAL,
                    CommercialLine.SOURCE_CONSIGNMENT,
                ],
            )
            .exclude(document__doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
            .select_related("document")
        )
        customer_total = sum((line.line_total for line in lines), Decimal("0.00"))
        owner_payout = sum((line_owner_payout(line) for line in lines), Decimal("0.00"))
        recognized_income = sum((line_recognized_income(line) for line in lines), Decimal("0.00"))
        return {
            "customer_total": customer_total.quantize(Decimal("0.01")),
            "revenue": recognized_income.quantize(Decimal("0.01")),
            "recognized_income": recognized_income.quantize(Decimal("0.01")),
            "cost": owner_payout.quantize(Decimal("0.01")),
            "owner_payout": owner_payout.quantize(Decimal("0.01")),
            "profit": recognized_income.quantize(Decimal("0.01")),
        }

    @staticmethod
    def _document_margin(start_date):
        docs = recognized_documents(start_date=start_date)
        return queryset_financial_summary(docs)

    @staticmethod
    def _top_margin_lines(start_date):
        rows = []
        lines = (
            CommercialLine.objects.filter(
                document__issue_date__gte=start_date,
                document__status__in=RECOGNIZED_DOCUMENT_STATUSES,
            )
            .exclude(document__doc_type=CommercialDocument.TYPE_CREDIT_NOTE)
            .select_related("document", "product", "product__category")
        )
        for line in lines:
            rows.append(
                {
                    "description": line.description,
                    "document": line.document.number,
                    "source_type": line.get_source_type_display(),
                    "customer_total": line.line_total,
                    "revenue": line_recognized_income(line),
                    "recognized_income": line_recognized_income(line),
                    "cost": line_business_cost(line),
                    "owner_payout": line_owner_payout(line),
                    "profit": line_profit(line),
                    "margin": line_margin_percent(line),
                }
            )
        rows.sort(key=lambda row: row["profit"], reverse=True)
        return rows[:10]

    @staticmethod
    def _top_customers(start_date):
        docs = recognized_documents(start_date=start_date).select_related("customer")
        rows = {}
        for document in docs:
            key = document.customer_id or f"walkin:{document.display_customer_name}"
            row = rows.setdefault(
                key,
                {
                    "customer": document.display_customer_name,
                    "documents": 0,
                    "revenue": Decimal("0.00"),
                    "recognized_income": Decimal("0.00"),
                    "customer_total": Decimal("0.00"),
                    "balance": Decimal("0.00"),
                },
            )
            row["documents"] += 1
            row["revenue"] += document_recognized_income(document)
            row["recognized_income"] += document_recognized_income(document)
            row["customer_total"] += document_customer_total(document)
            row["balance"] += document.balance_due
        ordered = sorted(rows.values(), key=lambda row: row["recognized_income"], reverse=True)
        return ordered[:10]


def staff_export_documents_csv(request):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.view_document_margin")
    ):
        raise Http404
    documents = CommercialDocument.objects.select_related(
        "customer", "salesperson"
    ).prefetch_related("lines").order_by("-issue_date", "-id")
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
            "customer_total",
            "recognized_income",
            "owner_payout",
            "business_cost",
            "business_profit",
            "tax",
            "withholding",
            "paid",
            "balance",
            "salesperson",
        ]
    )
    for document in documents[:5000]:
        if is_recognized_document(document):
            recognized_income = document_recognized_income(document)
            owner_payout = document_owner_payout(document)
            business_cost = document_business_cost(document)
            business_profit = recognized_income - business_cost
        else:
            recognized_income = Decimal("0.00")
            owner_payout = Decimal("0.00")
            business_cost = Decimal("0.00")
            business_profit = Decimal("0.00")
        writer.writerow(
            [
                document.number,
                document.doc_type,
                document.status,
                document.display_customer_name,
                document.issue_date,
                document.due_date or "",
                document_customer_total(document),
                recognized_income,
                owner_payout,
                business_cost,
                business_profit,
                document.tax_amount,
                document.withholding_tax_amount,
                document.amount_paid,
                document.balance_due,
                document.salesperson.get_username() if document.salesperson else "",
            ]
        )
    return response


def staff_export_customer_value_csv(request):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.view_document_margin")
    ):
        raise Http404
    start_90 = timezone.localdate() - timedelta(days=90)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="customer_value_90d.csv"'
    writer = csv.writer(response)
    writer.writerow(["customer", "documents", "recognized_income", "customer_total", "balance"])
    for row in ReportsHomeView._top_customers(start_90):
        writer.writerow(
            [
                row["customer"],
                row["documents"],
                row["recognized_income"],
                row["customer_total"],
                row["balance"],
            ]
        )
    return response


def staff_export_margin_lines_csv(request):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.view_document_margin")
    ):
        raise Http404
    start_30 = timezone.localdate() - timedelta(days=30)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="margin_lines_30d.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "description",
            "document",
            "source_type",
            "customer_total",
            "recognized_income",
            "owner_payout",
            "business_cost",
            "profit",
            "margin_percent",
        ]
    )
    for row in ReportsHomeView._top_margin_lines(start_30):
        writer.writerow(
            [
                row["description"],
                row["document"],
                row["source_type"],
                row["customer_total"],
                row["recognized_income"],
                row["owner_payout"],
                row["cost"],
                row["profit"],
                row["margin"],
            ]
        )
    return response


def staff_export_partner_payables_csv(request):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.view_document_margin")
    ):
        raise Http404
    start_30 = timezone.localdate() - timedelta(days=30)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="partner_payables_30d.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "partner_or_technician",
            "category",
            "documents",
            "lines",
            "customer_total",
            "amount_due",
            "recognized_income",
            "profit",
        ]
    )
    for row in partner_payables_summary(payable_lines(start_date=start_30)):
        writer.writerow(
            [
                row["partner"],
                row["category"],
                row["document_count"],
                row["line_count"],
                row["customer_total"],
                row["amount_due"],
                row["recognized_income"],
                row["profit"],
            ]
        )
    return response
