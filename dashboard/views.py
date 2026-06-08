from django.utils import timezone
from django.views.generic import TemplateView

from django.db.models import Avg, Q

from billing.models import CommercialDocument
from catalog.models import ProductReview
from catalog.stock_alerts import low_stock_products
from commerce.models import Order
from core.filters import apply_job_filters, apply_ticket_filters
from core.mixins import StaffRequiredMixin
from core.models import ContactMessage, SupportTicket
from operations.models import JobCard, JobFeedback


class StaffDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx["orders_today"] = Order.objects.filter(placed_at__date=today).count()
        ctx["open_jobs"] = JobCard.objects.exclude(
            status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
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
            JobFeedback.objects.select_related("job", "job__customer").order_by("-submitted_at")[:6]
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
        ctx["recent_documents"] = CommercialDocument.objects.select_related(
            "customer"
        ).order_by("-issue_date", "-id")[:8]
        return ctx
