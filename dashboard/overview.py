"""Read-only, permission-aware summaries over existing business records."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from automation.models import AutomationControl, AutomationJob, AutomationRun
from billing.models import AccountPayment, CommercialDocument, DocumentPayment
from commerce.models import Order
from core.models import SupportTicket
from marketing.models import MarketingLead
from operations.models import JobCard
from reports.models import CustomerFollowUp


def dashboard_overview(user, counts):
    now = timezone.now()
    today = timezone.localdate()
    access = counts["dashboard_access"]
    actions = []

    def add(priority, label, count, url, detail=""):
        if count:
            actions.append({
                "priority": priority, "label": label, "count": count,
                "url": url, "detail": detail,
            })

    if access["finance"]:
        add("Critical", "overdue invoice", counts["overdue_invoice_count"],
            reverse("staff_documents") + "?type=invoice",
            "Outstanding: {:,.0f}".format(counts["overdue_invoice_balance"]))
    if access["payments"]:
        add("Today", "payment awaiting verification", counts["pending_payment_count"],
            reverse("staff_payment_reconciliation"))
    if access["leads"]:
        add("Today", "overdue sales lead", counts["overdue_lead_count"],
            reverse("staff_marketing_leads") + "?follow_up=needs_attention")
    if access["followups"]:
        add("Soon", "customer follow-up", counts["pending_retention_followup_count"],
            reverse("staff_retention_dashboard"))
    if access["jobs"]:
        add("Critical", "overdue job", counts["overdue_jobs"],
            reverse("staff_jobs") + "?due=overdue")
    if access["tickets"]:
        add("Today", "overdue ticket", counts["overdue_tickets"],
            reverse("staff_tickets") + "?due=overdue")
    if access["products"]:
        add("Today", "low-stock item", counts["low_stock_count"],
            reverse("staff_products") + "?low=1")
    if access["automation"]:
        add("Critical", "failed automation job",
            counts["failed_automation_count"], reverse("staff_automation_control"),
            "Last 24 hours")
    if access["contacts"]:
        add("Today", "unhandled contact", counts["unhandled_contacts"],
            reverse("staff_contact_messages") + "?handled=0")
    if access["system"] and counts["backup_requires_attention"]:
        add("Critical", "backup requiring review", 1, "#operational-health")
    rank = {"Critical": 0, "Today": 1, "Soon": 2}
    actions.sort(key=lambda item: rank[item["priority"]])

    # Each employee sees shortcuts they are allowed to use, ordered by
    # operational urgency instead of an identical manager dashboard menu.
    focus_actions = []
    def focus(label, url, detail, count=0):
        focus_actions.append({
            "label": label, "url": url, "detail": detail, "count": count,
        })

    if access["leads"]:
        mine_count = MarketingLead.objects.filter(
            assigned_to=user,
            status__in=[
                MarketingLead.STATUS_NEW,
                MarketingLead.STATUS_CONTACTED,
                MarketingLead.STATUS_QUALIFIED,
            ],
        ).count()
        focus("Sales enquiries", reverse("staff_marketing_leads") + "?owner=mine",
              "Follow up on your assigned enquiries", mine_count)
        focus("Unassigned leads", reverse("staff_marketing_leads") + "?owner=unassigned",
              "Claim an enquiry before responding")
    if access["jobs"]:
        focus("Technician bench", reverse("staff_job_bench"),
              "Start or update repair work", counts["overdue_jobs"])
    if access["tickets"]:
        focus("Support queue", reverse("staff_tickets") + "?due=overdue",
              "Resolve overdue customer requests", counts["overdue_tickets"])
    if access["orders"]:
        focus("Active orders", reverse("staff_orders") + "?queue=active",
              "Prepare, dispatch or collect orders", counts.get("orders_in_transit", 0))
    if access["payments"]:
        focus("Verify payments", reverse("staff_payment_reconciliation"),
              "Check customer payment evidence", counts["pending_payment_count"])
    if access["products"]:
        focus("Inventory alerts", reverse("staff_products") + "?low=1",
              "Review stock before accepting new orders", counts["low_stock_count"])

    work = []
    if access["jobs"]:
        for job in (JobCard.objects.filter(assigned_to=user)
                    .exclude(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED])
                    .select_related("customer").order_by("scheduled_for", "pk")[:5]):
            work.append({
                "label": job.title, "kind": "Job",
                "url": reverse("staff_job_detail", args=[job.pk]),
                "customer": job.customer.name,
                "due": job.scheduled_for or now + timedelta(days=365),
            })
    if access["tickets"]:
        for ticket in (SupportTicket.objects.filter(assigned_to=user)
                       .exclude(status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED])
                       .select_related("customer").order_by("-updated_at", "-pk")[:5]):
            work.append({
                "label": ticket.subject, "kind": "Ticket",
                "url": reverse("staff_ticket_detail", args=[ticket.pk]),
                "customer": ticket.customer.name,
                "due": ticket.sla_due_at or now + timedelta(days=365),
            })
    if access["leads"]:
        for lead in (MarketingLead.objects.filter(
                assigned_to=user, status__in=[
                    MarketingLead.STATUS_NEW, MarketingLead.STATUS_CONTACTED,
                    MarketingLead.STATUS_QUALIFIED,
                ]).select_related("product").order_by("response_due_at", "pk")[:5]):
            work.append({
                "label": lead.name, "kind": "Lead",
                "url": reverse("staff_marketing_lead_edit", args=[lead.pk]),
                "customer": lead.product.name if lead.product_id else lead.get_status_display(),
                "due": lead.next_follow_up_at or lead.response_due_at or now + timedelta(days=365),
            })
    if access["followups"]:
        for followup in (CustomerFollowUp.objects.filter(
                assigned_to=user, status__in=[
                    CustomerFollowUp.STATUS_PENDING, CustomerFollowUp.STATUS_IN_PROGRESS,
                ]).select_related("customer").order_by("due_at", "pk")[:5]):
            work.append({
                "label": followup.get_follow_up_type_display(), "kind": "Follow-up",
                "url": reverse("staff_retention_dashboard"),
                "customer": followup.customer.name, "due": followup.due_at,
            })
    work.sort(key=lambda item: item["due"])
    result = {
        "action_center": actions, "my_work": work[:8],
        "staff_focus_actions": focus_actions[:7],
        "show_sales_insights": access["orders"] or access["finance"],
    }
    if access["orders"]:
        active = Order.objects.exclude(status=Order.STATUS_CANCELLED)
        start = now - timedelta(days=7)
        result["order_value_7d"] = active.filter(placed_at__gte=start).aggregate(
            total=Sum("total"))["total"] or Decimal("0")
        result["order_value_previous_7d"] = active.filter(
            placed_at__gte=start - timedelta(days=7), placed_at__lt=start
        ).aggregate(total=Sum("total"))["total"] or Decimal("0")
        result["order_value_today"] = active.filter(placed_at__date=today).aggregate(
            total=Sum("total"))["total"] or Decimal("0")
        daily = {
            row["day"]: row["total"] for row in
            active.filter(placed_at__date__gte=today - timedelta(days=6))
            .annotate(day=TruncDate("placed_at", tzinfo=timezone.get_current_timezone()))
            .values("day").annotate(total=Sum("total")).order_by("day")
        }
        result["order_value_trend"] = [
            {"label": (today - timedelta(days=i)).strftime("%a %d"),
             "value": daily.get(today - timedelta(days=i), Decimal("0"))}
            for i in range(6, -1, -1)
        ]
    if access["finance"]:
        current = today - timedelta(days=6)
        previous = today - timedelta(days=13)
        invoices = CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_INVOICE
        ).exclude(status__in=[
            CommercialDocument.STATUS_DRAFT, CommercialDocument.STATUS_CANCELLED,
            CommercialDocument.STATUS_EXPIRED,
        ])
        result["invoiced_7d"] = invoices.filter(issue_date__gte=current).aggregate(
            total=Sum("total"))["total"] or Decimal("0")
        result["invoiced_previous_7d"] = invoices.filter(
            issue_date__gte=previous, issue_date__lt=current
        ).aggregate(total=Sum("total"))["total"] or Decimal("0")
        payment_start = now - timedelta(days=7)
        result["payments_recorded_7d"] = (
            (DocumentPayment.objects.filter(recorded_at__gte=payment_start)
             .aggregate(total=Sum("amount"))["total"] or Decimal("0"))
            + (AccountPayment.objects.filter(recorded_at__gte=payment_start)
               .aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        )
        result["receivables_balance"] = counts["outstanding_invoice_balance"]
    if access["automation"]:
        control = AutomationControl.objects.filter(singleton_key="primary").first()
        due = AutomationJob.objects.filter(
            status__in=[AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY])
        heartbeat = control.last_heartbeat_at if control else None
        delayed = not heartbeat or heartbeat < now - timedelta(minutes=30)
        last_success = AutomationRun.objects.filter(
            status=AutomationRun.STATUS_SUCCEEDED).order_by("-finished_at").first()
        result["automation_summary"] = {
            "status": ("Paused" if control and control.is_paused else
                       "Delayed" if delayed else
                       "Failed" if counts["failed_automation_count"] else "Healthy"),
            "heartbeat": heartbeat, "queued": due.count(),
            "oldest_due": due.order_by("next_attempt_at").values_list(
                "next_attempt_at", flat=True).first(),
            "failed": counts["failed_automation_count"],
            "last_success": last_success.finished_at if last_success else None,
        }
    if access["system"]:
        health = []
        if access["finance"]:
            health.append({"label": "Cash", "count": counts["overdue_invoice_count"],
                           "url": reverse("staff_documents") + "?type=invoice"})
        if access["leads"]:
            health.append({"label": "Customers", "count": counts["overdue_lead_count"],
                           "url": reverse("staff_marketing_leads")})
        if access["products"]:
            health.append({"label": "Inventory", "count": counts["low_stock_count"],
                           "url": reverse("staff_products") + "?low=1"})
        if access["jobs"]:
            health.append({"label": "Operations", "count": counts["overdue_jobs"],
                           "url": reverse("staff_jobs") + "?due=overdue"})
        if access["automation"]:
            health.append({"label": "System", "count": counts["failed_automation_count"]
                           + int(counts["backup_requires_attention"]),
                           "url": reverse("staff_automation_control")})
        result["business_health"] = health
    return result
