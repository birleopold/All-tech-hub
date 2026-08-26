from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from automation.connectors import channel_is_configured, diagnose_channel
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
    SocialAutopilotForm,
)
from automation.models import AutomationJob, SocialAutopilotSettings
from automation.reporting import (
    automation_control_summary,
    automation_integrity_findings,
    social_channel_performance,
)
from catalog.models import Product
from core.mixins import StaffRequiredMixin
from marketing.models import ScheduledPost


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
        autopilot = SocialAutopilotSettings.load()
        context["autopilot"] = autopilot
        context["autopilot_form"] = SocialAutopilotForm(instance=autopilot)
        from automation.autopilot import autopilot_readiness
        context["autopilot_readiness"] = autopilot_readiness(autopilot)
        context["social_performance"] = social_channel_performance(days=30)
        context["social_connections"] = {
            channel: channel_is_configured(channel)
            for channel in ("facebook", "instagram", "telegram")
        }
        context["upcoming_social_posts"] = (
            ScheduledPost.objects.filter(
                status__in=[
                    ScheduledPost.STATUS_DRAFT,
                    ScheduledPost.STATUS_SCHEDULED,
                    ScheduledPost.STATUS_READY,
                ]
            )
            .select_related("product")
            .order_by("scheduled_for", "pk")[:20]
        )
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


@require_POST
def social_autopilot_update(request):
    _require_automation_staff(request, change=True)
    autopilot = SocialAutopilotSettings.load()
    form = SocialAutopilotForm(request.POST, instance=autopilot)
    if not form.is_valid():
        context = automation_control_summary()
        context["integrity"] = automation_integrity_findings()
        context["pause_form"] = AutomationPauseForm()
        context["resume_form"] = AutomationResumeForm()
        context["can_change_automation"] = True
        context["job_type_labels"] = dict(AutomationJob.TYPE_CHOICES)
        context["autopilot"] = autopilot
        context["autopilot_form"] = form
        from automation.autopilot import autopilot_readiness
        context["autopilot_readiness"] = autopilot_readiness(autopilot)
        context["social_performance"] = social_channel_performance(days=30)
        context["social_connections"] = {
            channel: channel_is_configured(channel)
            for channel in ("facebook", "instagram", "telegram")
        }
        context["upcoming_social_posts"] = (
            ScheduledPost.objects.filter(
                status__in=[
                    ScheduledPost.STATUS_DRAFT,
                    ScheduledPost.STATUS_SCHEDULED,
                    ScheduledPost.STATUS_READY,
                ]
            )
            .select_related("product")
            .order_by("scheduled_for", "pk")[:20]
        )
        return render(request, "automation/staff_control.html", context, status=400)

    autopilot = form.save()
    from automation.autopilot import (
        generate_autopilot_calendar,
        reconcile_autopilot_state,
    )

    reconciled = reconcile_autopilot_state(autopilot)
    if autopilot.enabled:
        result = generate_autopilot_calendar()
        messages.success(
            request,
            f"Social autopilot saved. {result.get('created', 0)} channel post(s) generated.",
        )
    else:
        messages.success(
            request,
            f"Social autopilot stopped. {reconciled['changed']} future delivery record(s) were stopped.",
        )
    return redirect("staff_automation_control")


@require_POST
def social_autopilot_promote_product(request, product_id: int):
    _require_automation_staff(request, change=True)
    product = get_object_or_404(Product, pk=product_id)
    from automation.autopilot import queue_product_promotion

    result = queue_product_promotion(product, actor=request.user)
    if result.get("error"):
        messages.error(request, result["error"])
    elif result.get("automatic"):
        messages.success(
            request,
            f"{result['created']} social post(s) queued for automatic publishing.",
        )
    else:
        messages.success(
            request,
            f"{result['created']} social draft(s) created for review.",
        )
    return redirect("staff_product_edit", pk=product.pk)


@require_POST
def social_autopilot_rebuild(request):
    _require_automation_staff(request, change=True)
    from automation.autopilot import rebuild_autopilot_calendar

    result = rebuild_autopilot_calendar()
    messages.success(
        request,
        (
            f"Social calendar rebuilt: {result['cancelled']} old future post(s) "
            f"cancelled and {result['created']} new channel post(s) generated."
        ),
    )
    return redirect("staff_automation_control")


@require_POST
def social_autopilot_test_connections(request):
    _require_automation_staff(request, change=True)
    autopilot = SocialAutopilotSettings.load()
    channels = autopilot.channels or ["facebook", "instagram", "telegram"]
    for channel in channels:
        result = diagnose_channel(channel)
        text = f"{channel.title()}: {result['message']}"
        if result["ok"]:
            messages.success(request, text)
        else:
            messages.error(request, text)
    return redirect("staff_automation_control")


@require_POST
def social_autopilot_cancel_post(request, post_id: int):
    _require_automation_staff(request, change=True)
    post = get_object_or_404(ScheduledPost, pk=post_id)
    from automation.autopilot import cancel_autopilot_post

    result = cancel_autopilot_post(post, actor=request.user)
    if result.get("cancelled"):
        messages.success(request, "The selected social post was removed from the queue.")
    else:
        messages.error(request, result.get("error") or "The social post could not be removed.")
    return redirect("staff_automation_control")
