from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import CommercialDocument
from catalog.models import Product, ProductReview
from catalog.quality import catalogue_quality_rows, catalogue_quality_summary
from catalog.stock_alerts import low_stock_products
from commerce.models import Order
from core.backups import latest_backup_status
from core.filters import apply_job_filters, apply_ticket_filters
from core.mixins import StaffRequiredMixin
from core.models import ContactMessage, SupportTicket
from core.seo_audit import seo_audit_snapshot
from operations.models import JobCard, JobFeedback


class StaffDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        now = timezone.now()
        terminal_job_statuses = [JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]

        ctx["orders_today"] = Order.objects.filter(placed_at__date=today).count()
        ctx["orders_in_transit"] = Order.objects.filter(
            status=Order.STATUS_DISPATCHED
        ).count()
        ctx["open_jobs"] = JobCard.objects.exclude(
            status__in=terminal_job_statuses
        ).count()
        ctx["draft_quotes"] = CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_QUOTE,
            status=CommercialDocument.STATUS_DRAFT,
        ).count()
        ctx["open_tickets"] = SupportTicket.objects.exclude(
            status__in=(SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED)
        ).count()
        ctx["unhandled_contacts"] = ContactMessage.objects.filter(handled=False).count()
        ctx["low_stock_count"] = len(low_stock_products(limit=None))
        ctx["pending_reviews"] = ProductReview.objects.filter(is_published=False).count()
        avg = JobFeedback.objects.aggregate(avg=Avg("rating"))["avg"]
        ctx["avg_job_rating"] = round(float(avg), 1) if avg is not None else None
        ctx["recent_feedback"] = list(
            JobFeedback.objects.select_related("job", "job__customer").order_by(
                "-submitted_at"
            )[:6]
        )
        ctx["overdue_jobs"] = apply_job_filters(
            JobCard.objects.all(), {"due": "overdue"}
        ).count()
        ctx["overdue_tickets"] = apply_ticket_filters(
            SupportTicket.objects.all(), {"due": "overdue"}
        ).count()
        ctx["recent_orders"] = Order.objects.select_related("customer").order_by(
            "-placed_at"
        )[:8]
        ctx["recent_jobs"] = JobCard.objects.select_related("customer").order_by(
            "-received_on"
        )[:8]
        ctx["upcoming_jobs"] = (
            JobCard.objects.select_related("customer", "assigned_to")
            .filter(scheduled_for__gte=now)
            .exclude(status__in=terminal_job_statuses)
            .order_by("scheduled_for", "pk")[:5]
        )
        ctx["recent_documents"] = CommercialDocument.objects.select_related(
            "customer"
        ).order_by("-created_at", "-id")[:8]

        quality_products = (
            Product.objects.filter(is_published=True)
            .select_related("category", "growth_data")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )
        quality_rows = catalogue_quality_rows(quality_products)
        ctx["catalogue_quality"] = catalogue_quality_summary(quality_rows)

        backup_status = latest_backup_status()
        ctx["backup_status"] = backup_status
        ctx["backup_requires_attention"] = (
            not backup_status.healthy
            or backup_status.age_hours is None
            or backup_status.age_hours > 48
        )
        seo_snapshot = seo_audit_snapshot()
        ctx["seo_score"] = seo_snapshot["score"]
        ctx["seo_requires_attention"] = bool(
            seo_snapshot["critical"] or seo_snapshot["warnings"]
        )
        return ctx


class CatalogueQualityView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/catalogue_quality.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = (
            Product.objects.select_related("category", "growth_data")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )

        query = (self.request.GET.get("q") or "").strip()
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(sku__icontains=query)
                | Q(category__name__icontains=query)
                | Q(growth_data__brand__icontains=query)
            ).distinct()

        publication = (self.request.GET.get("published") or "").strip()
        if publication == "1":
            products = products.filter(is_published=True)
        elif publication == "0":
            products = products.filter(is_published=False)

        all_rows = catalogue_quality_rows(products)
        status = (self.request.GET.get("status") or "").strip().lower()
        if status in {"ready", "attention", "critical"}:
            visible_rows = [row for row in all_rows if row.status == status]
        else:
            status = ""
            visible_rows = all_rows

        paginator = Paginator(visible_rows, 40)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "quality_rows": page_obj.object_list,
                "quality_summary": catalogue_quality_summary(all_rows),
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": paginator.num_pages > 1,
                "current_query": query,
                "current_status": status,
                "current_publication": publication,
            }
        )
        return context


class SEOControlCenterView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/seo_control_center.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo_audit_snapshot()
        return context
