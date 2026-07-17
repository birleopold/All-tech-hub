from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from automation.control import (
    AutomationControlError,
    cancel_open_job,
    pause_automation,
    replay_failed_job,
    resume_automation,
)
from automation.forms import (
    AutomationJobCancelForm,
    AutomationJobReplayForm,
    AutomationPauseForm,
    AutomationResumeForm,
)
from automation.models import AutomationJob
from automation.reporting import automation_control_summary, automation_integrity_findings
from core.mixins import StaffRequiredMixin


VIEW_PERMISSION = "automation.view_automationjob"
CHANGE_PERMISSION = "automation.change_automationjob"


class AutomationControlDashboardView(
    PermissionRequiredMixin,
    StaffRequiredMixin,
    TemplateView,
):
    permission_required = VIEW_PERMISSION
    raise_exception = True
    template_name = "automation/staff_control.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(automation_control_summary())
        context["integrity"] = automation_integrity_findings()
        context["pause_form"] = AutomationPauseForm()
        context["resume_form"] = AutomationResumeForm()
        context["can_change_automation"] = self.request.user.has_perm(CHANGE_PERMISSION)
        context["job_type_labels"] = dict(AutomationJob.TYPE_CHOICES)
        return context


def _require_automation_staff(request, *, change: bool = False):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    permission = CHANGE_PERMISSION if change else VIEW_PERMISSION
    if not request.user.has_perm(permission):
        raise PermissionDenied


def automation_job_detail(request, pk: int):
    _require_automation_staff(request)
    job = get_object_or_404(
        AutomationJob.objects.select_related("delivery", "delivery__post"),
        pk=pk,
    )
    return render(
        request,
        "automation/staff_job_detail.html",
        {
            "job": job,
            "events": job.events.select_related("actor")[:100],
            "replay_form": AutomationJobReplayForm(job=job),
            "cancel_form": AutomationJobCancelForm(job=job),
            "can_change_automation": request.user.has_perm(CHANGE_PERMISSION),
            "social_replay_blocked": job.job_type == AutomationJob.TYPE_SOCIAL_POST,
        },
    )


@require_POST
def automation_pause(request):
    _require_automation_staff(request, change=True)
    form = AutomationPauseForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The automation pause confirmation was not valid.")
        return redirect("staff_automation_control")
    scope = form.cleaned_data["scope"]
    selected = [] if scope == AutomationPauseForm.SCOPE_ALL else [scope]
    pause_automation(
        user=request.user,
        reason=form.cleaned_data["reason"],
        job_types=selected,
    )
    messages.success(request, "Automation pause applied.")
    return redirect("staff_automation_control")


@require_POST
def automation_resume(request):
    _require_automation_staff(request, change=True)
    form = AutomationResumeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The automation resume confirmation was not valid.")
        return redirect("staff_automation_control")
    scope = form.cleaned_data["scope"]
    selected = [] if scope == AutomationResumeForm.SCOPE_ALL else [scope]
    resume_automation(user=request.user, job_types=selected)
    messages.success(request, "Automation resume applied.")
    return redirect("staff_automation_control")


@require_POST
def automation_job_replay(request, pk: int):
    _require_automation_staff(request, change=True)
    job = get_object_or_404(AutomationJob, pk=pk)
    form = AutomationJobReplayForm(request.POST, job=job)
    if not form.is_valid():
        messages.error(request, "The replay confirmation was not valid.")
        return redirect("staff_automation_job_detail", pk=job.pk)
    try:
        replay_failed_job(job, user=request.user)
    except AutomationControlError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "The reviewed job was returned to the queue.")
    return redirect("staff_automation_job_detail", pk=job.pk)


@require_POST
def automation_job_cancel(request, pk: int):
    _require_automation_staff(request, change=True)
    job = get_object_or_404(AutomationJob, pk=pk)
    form = AutomationJobCancelForm(request.POST, job=job)
    if not form.is_valid():
        messages.error(request, "The cancellation confirmation was not valid.")
        return redirect("staff_automation_job_detail", pk=job.pk)
    try:
        cancel_open_job(
            job,
            user=request.user,
            reason=form.cleaned_data.get("reason") or "",
        )
    except AutomationControlError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "The queued automation job was cancelled.")
    return redirect("staff_automation_job_detail", pk=job.pk)
