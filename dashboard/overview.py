"""Read-only dashboard summaries over existing business records."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from automation.models import AutomationControl, AutomationJob
from commerce.models import Order
from core.models import SupportTicket
from operations.models import JobCard


def dashboard_overview(user, counts):
    now = timezone.now()
    today = timezone.localdate()
    roles = set(user.groups.values_list("name", flat=True))
    manager = user.is_superuser or "Manager" in roles or not roles
    def has(*names):
        return manager or bool(roles.intersection(names))

    actions = []
    def add(priority, label, count, url, detail=""):
        if count:
            actions.append(dict(priority=priority, label=label, count=count, url=url, detail=detail))

    if has("Finance"):
        add("Critical", "overdue invoice", counts["overdue_invoice_count"],
            reverse("staff_documents") + "?type=invoice",
            "Outstanding: {:,.0f}".format(counts["overdue_invoice_balance"]))
        add("Today", "payment awaiting verification", counts["pending_payment_count"],
            reverse("staff_payment_reconciliation"))
    if has("Sales"):
        add("Today", "overdue sales lead", counts["overdue_lead_count"],
            reverse("staff_marketing_leads"))
        add("Soon", "customer follow-up", counts["pending_retention_followup_count"],
            reverse("staff_retention_dashboard"))
    if has("Technician"):
        add("Critical", "overdue job", counts["overdue_jobs"],
            reverse("staff_jobs") + "?due=overdue")
        add("Today", "overdue ticket", counts["overdue_tickets"],
            reverse("staff_tickets") + "?due=overdue")
    if has("Inventory"):
        add("Today", "low-stock item", counts["low_stock_count"],
            reverse("staff_products") + "?low=1")
    if manager:
        add("Critical", "failed automation job", counts["failed_automation_count"],
            reverse("staff_automation_control"))
        add("Today", "unhandled contact", counts["unhandled_contacts"],
            reverse("staff_contact_messages") + "?handled=0")
        if counts["backup_requires_attention"]:
            add("Critical", "backup requiring review", 1, "#operational-health")
    rank = {"Critical": 0, "Today": 1, "Soon": 2}
    actions.sort(key=lambda item: rank[item["priority"]])

    work = []
    for job in (JobCard.objects.filter(assigned_to=user)
                .exclude(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED])
                .select_related("customer").order_by("scheduled_for", "pk")[:5]):
        work.append(dict(label=job.title, kind="Job", url=reverse("staff_job_detail", args=[job.pk]),
                         customer=job.customer.name))
    for ticket in (SupportTicket.objects.filter(assigned_to=user)
                   .exclude(status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED])
                   .select_related("customer").order_by("-updated_at", "-pk")[:5]):
        work.append(dict(label=ticket.subject, kind="Ticket",
                         url=reverse("staff_ticket_detail", args=[ticket.pk]),
                         customer=ticket.customer.name))

    result = {"action_center": actions, "my_work": work[:8], "dashboard_roles": sorted(roles),
              "show_sales_insights": has("Sales", "Finance")}
    if result["show_sales_insights"]:
        active = Order.objects.exclude(status=Order.STATUS_CANCELLED)
        def period(start, end):
            return active.filter(placed_at__gte=start, placed_at__lt=end).aggregate(
                total=Sum("total"))["total"] or Decimal("0")
        start = now - timedelta(days=7)
        result["order_value_7d"] = period(start, now)
        result["order_value_previous_7d"] = period(start - timedelta(days=7), start)
        result["order_value_today"] = active.filter(placed_at__date=today).aggregate(
            total=Sum("total"))["total"] or Decimal("0")
        result["order_value_trend"] = [
            {"label": (today - timedelta(days=i)).strftime("%a %d"),
             "value": active.filter(placed_at__date=today - timedelta(days=i)).aggregate(
                 total=Sum("total"))["total"] or Decimal("0")}
            for i in range(6, -1, -1)
        ]
    if manager:
        control = AutomationControl.objects.filter(singleton_key="primary").first()
        queued = AutomationJob.objects.filter(status__in=[
            AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY]).count()
        heartbeat = control.last_heartbeat_at if control else None
        delayed = not heartbeat or heartbeat < now - timedelta(minutes=30)
        result["automation_summary"] = {
            "status": ("Paused" if control and control.is_paused else
                       "Failed" if counts["failed_automation_count"] else
                       "Delayed" if delayed else "Healthy"),
            "heartbeat": heartbeat, "queued": queued,
            "failed": counts["failed_automation_count"],
            "next_run": AutomationJob.objects.filter(status__in=[
                AutomationJob.STATUS_QUEUED, AutomationJob.STATUS_RETRY
            ]).order_by("next_attempt_at").values_list("next_attempt_at", flat=True).first(),
        }
        result["business_health"] = [
            {"label": "Cash", "count": counts["overdue_invoice_count"], "url": reverse("staff_documents") + "?type=invoice"},
            {"label": "Customers", "count": counts["overdue_lead_count"], "url": reverse("staff_marketing_leads")},
            {"label": "Inventory", "count": counts["low_stock_count"], "url": reverse("staff_products") + "?low=1"},
            {"label": "Operations", "count": counts["overdue_jobs"] + counts["overdue_tickets"], "url": reverse("staff_jobs") + "?due=overdue"},
            {"label": "System", "count": counts["failed_automation_count"] + int(counts["backup_requires_attention"]), "url": reverse("staff_automation_control")},
        ]
    return result
