from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.mixins import StaffRequiredMixin
from reports.followups import (
    close_followup,
    customer_outreach_allowed,
    open_followup_whatsapp,
    refresh_retention_followups,
    send_followup_email,
)
from reports.models import CustomerFollowUp
from reports.retention import retention_summary


class RetentionDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "reports/retention_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            days = int(self.request.GET.get("days") or 90)
        except (TypeError, ValueError):
            days = 90
        context["retention"] = retention_summary(days)
        tasks = list(
            CustomerFollowUp.objects.filter(
                status__in=[
                    CustomerFollowUp.STATUS_PENDING,
                    CustomerFollowUp.STATUS_IN_PROGRESS,
                ]
            ).select_related(
                "customer", "assigned_to", "product_serial", "product_serial__product"
            ).order_by("due_at", "-priority")[:100]
        )
        for task in tasks:
            task.email_allowed = customer_outreach_allowed(task, "email")
            task.whatsapp_allowed = customer_outreach_allowed(task, "whatsapp")
            task.is_overdue = task.due_at < timezone.now()
        context["followups"] = tasks
        context["recent_closed_followups"] = CustomerFollowUp.objects.exclude(
            status__in=[
                CustomerFollowUp.STATUS_PENDING,
                CustomerFollowUp.STATUS_IN_PROGRESS,
            ]
        ).select_related("customer", "completed_by")[:20]
        return context


def _staff_followup(request, pk):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    return get_object_or_404(CustomerFollowUp, pk=pk)


@require_POST
def refresh_customer_followups(request):
    if not request.user.is_staff:
        raise Http404
    result = refresh_retention_followups(limit=100)
    messages.success(
        request,
        f"Customer-care queue refreshed: {result['warranty_created']} warranty "
        f"and {result['dormant_created']} dormant-customer task(s) created.",
    )
    return redirect("staff_retention_dashboard")


@require_POST
def customer_followup_claim(request, pk):
    task = _staff_followup(request, pk)
    if not task.is_open:
        messages.error(request, "This follow-up is already closed.")
    else:
        task.assigned_to = request.user
        task.status = CustomerFollowUp.STATUS_IN_PROGRESS
        task.save(update_fields=["assigned_to", "status", "updated_at"])
        messages.success(request, "Customer follow-up assigned to you.")
    return redirect("staff_retention_dashboard")


@require_POST
def customer_followup_email(request, pk):
    task = _staff_followup(request, pk)
    try:
        send_followup_email(task, actor=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Customer follow-up email sent and recorded.")
    return redirect("staff_retention_dashboard")


@require_POST
def customer_followup_whatsapp(request, pk):
    task = _staff_followup(request, pk)
    try:
        url = open_followup_whatsapp(task, actor=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_retention_dashboard")
    return redirect(url)


@require_POST
def customer_followup_close(request, pk):
    task = _staff_followup(request, pk)
    dismissed = request.POST.get("action") == "dismiss"
    try:
        close_followup(
            task,
            actor=request.user,
            dismissed=dismissed,
            note=request.POST.get("note", ""),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            "Customer follow-up dismissed." if dismissed else "Customer follow-up completed.",
        )
    return redirect("staff_retention_dashboard")
