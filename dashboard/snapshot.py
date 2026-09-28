"""Permission-aware data for the staff landing page."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Avg, F, Q, Sum
from django.utils import timezone

from automation.models import AutomationJob
from billing.models import CommercialDocument, PaymentSubmission
from catalog.models import Product, ProductReview
from catalog.quality import catalogue_quality_rows, catalogue_quality_summary
from catalog.stock_alerts import low_stock_products
from commerce.models import Order
from core.backups import latest_backup_status
from core.filters import apply_job_filters, apply_ticket_filters
from core.models import ContactMessage, SupportTicket
from core.seo_audit import seo_audit_snapshot
from marketing.models import MarketingLead
from operations.models import JobCard, JobFeedback
from reports.models import CustomerFollowUp


def _catalogue_summary():
    # A short bounded snapshot avoids walking every published listing on each visit.
    key = "staff_dashboard:catalogue_quality:v2"
    summary = cache.get(key)
    if summary is None:
        products = (Product.objects.filter(is_published=True)
                    .select_related("category", "growth_data")
                    .prefetch_related("gallery_images", "variants"))
        summary = catalogue_quality_summary(catalogue_quality_rows(products))
        cache.set(key, summary, 60)
    return summary


def dashboard_snapshot(user):
    now = timezone.now()
    today = timezone.localdate()
    can = {
        "orders": user.has_perm("commerce.view_order"),
        "documents": user.has_perm("billing.view_commercialdocument"),
        "finance": user.has_perm("billing.view_documentpayment"),
        "payments": user.has_perm("billing.change_documentpayment"),
        "jobs": user.has_perm("operations.view_jobcard"),
        "tickets": user.has_perm("core.view_supportticket"),
        "leads": user.has_perm("marketing.view_marketinglead"),
        "followups": user.has_perm("reports.view_customerfollowup"),
        "products": user.has_perm("catalog.view_product"),
        "contacts": user.has_perm("core.view_contactmessage"),
        "automation": user.has_perm("automation.view_automationjob"),
        "system": user.has_perm("core.view_auditevent"),
    }
    data = {
        "dashboard_access": can,
        "orders_today": 0, "orders_in_transit": 0, "open_jobs": 0,
        "draft_quotes": 0, "open_tickets": 0, "unhandled_contacts": 0,
        "low_stock_count": 0, "pending_reviews": 0,
        "overdue_invoice_count": 0, "overdue_invoice_balance": Decimal("0"),
        "outstanding_invoice_balance": Decimal("0"), "pending_payment_count": 0,
        "failed_automation_count": 0, "pending_retention_followup_count": 0,
        "overdue_lead_count": 0, "overdue_jobs": 0, "overdue_tickets": 0,
        "avg_job_rating": None, "recent_feedback": [], "recent_orders": [],
        "recent_jobs": [], "upcoming_jobs": [], "recent_documents": [],
        "catalogue_quality": {}, "backup_status": None,
        "backup_requires_attention": False, "seo_score": None,
        "seo_requires_attention": False,
    }
    if can["orders"]:
        data["orders_today"] = Order.objects.filter(placed_at__date=today).count()
        data["orders_in_transit"] = Order.objects.filter(status=Order.STATUS_DISPATCHED).count()
        data["recent_orders"] = Order.objects.select_related("customer").order_by("-placed_at")[:8]
    if can["documents"]:
        data["draft_quotes"] = CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_QUOTE,
            status=CommercialDocument.STATUS_DRAFT,
        ).count()
        data["recent_documents"] = CommercialDocument.objects.select_related(
            "customer").order_by("-created_at", "-id")[:8]
    if can["finance"]:
        outstanding = CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_INVOICE,
        ).exclude(status__in=[
            CommercialDocument.STATUS_PAID, CommercialDocument.STATUS_CANCELLED,
            CommercialDocument.STATUS_EXPIRED,
        ]).filter(total__gt=F("amount_paid"))
        overdue = outstanding.filter(due_date__lt=today)
        data["overdue_invoice_count"] = overdue.count()
        data["overdue_invoice_balance"] = overdue.aggregate(
            total=Sum(F("total") - F("amount_paid")))["total"] or Decimal("0")
        data["outstanding_invoice_balance"] = outstanding.aggregate(
            total=Sum(F("total") - F("amount_paid")))["total"] or Decimal("0")
    if can["payments"]:
        data["pending_payment_count"] = PaymentSubmission.objects.filter(
            status=PaymentSubmission.STATUS_PENDING).count()
    if can["jobs"]:
        closed = [JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
        data["open_jobs"] = JobCard.objects.exclude(status__in=closed).count()
        data["overdue_jobs"] = apply_job_filters(
            JobCard.objects.all(), {"due": "overdue"}).count()
        data["recent_jobs"] = JobCard.objects.select_related("customer").order_by("-received_on")[:8]
        data["upcoming_jobs"] = (
            JobCard.objects.select_related("customer", "assigned_to")
            .filter(scheduled_for__gte=now).exclude(status__in=closed)
            .order_by("scheduled_for", "pk")[:5]
        )
        avg = JobFeedback.objects.aggregate(avg=Avg("rating"))["avg"]
        data["avg_job_rating"] = round(float(avg), 1) if avg is not None else None
        data["recent_feedback"] = JobFeedback.objects.select_related(
            "job", "job__customer").order_by("-submitted_at")[:6]
    if can["tickets"]:
        data["open_tickets"] = SupportTicket.objects.exclude(status__in=(
            SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED)).count()
        data["overdue_tickets"] = apply_ticket_filters(
            SupportTicket.objects.all(), {"due": "overdue"}).count()
    if can["contacts"]:
        data["unhandled_contacts"] = ContactMessage.objects.filter(handled=False).count()
    if can["products"]:
        key = "staff_dashboard:low_stock:v2"
        low_count = cache.get(key)
        if low_count is None:
            low_count = len(low_stock_products(limit=None))
            cache.set(key, low_count, 60)
        data["low_stock_count"] = low_count
        data["pending_reviews"] = ProductReview.objects.filter(is_published=False).count()
        data["catalogue_quality"] = _catalogue_summary()
        seo = seo_audit_snapshot()
        data["seo_score"] = seo["score"]
        data["seo_requires_attention"] = bool(seo["critical"] or seo["warnings"])
    if can["automation"]:
        data["failed_automation_count"] = AutomationJob.objects.filter(
            status=AutomationJob.STATUS_FAILED,
            updated_at__gte=now - timedelta(days=1)).count()
    if can["followups"]:
        data["pending_retention_followup_count"] = CustomerFollowUp.objects.filter(
            status__in=[CustomerFollowUp.STATUS_PENDING,
                        CustomerFollowUp.STATUS_IN_PROGRESS]).count()
    if can["leads"]:
        data["overdue_lead_count"] = MarketingLead.objects.filter(
            status__in=[MarketingLead.STATUS_NEW, MarketingLead.STATUS_CONTACTED,
                        MarketingLead.STATUS_QUALIFIED]).filter(
            Q(next_follow_up_at__lte=now) |
            Q(status=MarketingLead.STATUS_NEW, first_contacted_at__isnull=True,
              response_due_at__lte=now)).count()
    if can["system"]:
        backup = latest_backup_status()
        data["backup_status"] = backup
        data["backup_requires_attention"] = (
            not backup.healthy or backup.age_hours is None or backup.age_hours > 48)
    return data
