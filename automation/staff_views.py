from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
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
from automation.models import (
    AutomationJob, PostChannelDelivery, SocialAutopilotSettings,
)
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


CHANNEL_LABELS = {
    "facebook": "Facebook Page",
    "instagram": "Instagram",
    "telegram": "Telegram",
}


def _social_autopilot_context(autopilot, *, form=None):
    from automation.autopilot import AUTOPILOT_MARKER, autopilot_readiness

    selected = list(autopilot.channels or [])
    connections = {
        channel: channel_is_configured(channel)
        for channel in CHANNEL_LABELS
    }
    upcoming = (
        ScheduledPost.objects.filter(
            Q(notes__startswith=AUTOPILOT_MARKER)
            | Q(notes__startswith="[social-priority]"),
            status__in=[
                ScheduledPost.STATUS_DRAFT,
                ScheduledPost.STATUS_SCHEDULED,
                ScheduledPost.STATUS_READY,
            ],
        )
        .select_related("product", "automation_plan")
        .order_by("scheduled_for", "pk")[:20]
    )
    failed_deliveries = list(
        PostChannelDelivery.objects.filter(
            status__in=[
                PostChannelDelivery.STATUS_FAILED,
                PostChannelDelivery.STATUS_MANUAL,
            ],
        )
        .select_related("post")
        .order_by("-updated_at", "-pk")[:12]
    )
    delivery_ids = [delivery.pk for delivery in failed_deliveries]
    jobs_by_delivery = {
        job.delivery_id: job.pk
        for job in AutomationJob.objects.filter(
            delivery_id__in=delivery_ids,
            job_type=AutomationJob.TYPE_SOCIAL_POST,
        )
    }
    failed_social_posts = [
        {"delivery": delivery, "job_id": jobs_by_delivery.get(delivery.pk)}
        for delivery in failed_deliveries
    ]
    selected_labels = [
        CHANNEL_LABELS[channel] for channel in selected if channel in CHANNEL_LABELS
    ]
    return {
        "autopilot": autopilot,
        "autopilot_form": form or SocialAutopilotForm(instance=autopilot),
        "autopilot_readiness": autopilot_readiness(autopilot),
        "social_performance": social_channel_performance(days=30),
        "social_connections": connections,
        "social_channel_statuses": [
            {
                "key": channel,
                "label": label,
                "connected": connections[channel],
                "selected": channel in selected,
            }
            for channel, label in CHANNEL_LABELS.items()
        ],
        "selected_channel_labels": selected_labels,
        "selected_channel_names": ", ".join(selected_labels) or "No channels selected",
        "daily_post_count": len(autopilot.posting_hours or [9]),
        "target_delivery_count": (
            len(selected) * len(autopilot.posting_hours or [9]) * autopilot.queue_days
        ),
        "upcoming_social_posts": upcoming,
        "failed_social_posts": failed_social_posts,
    }


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
        context.update(_social_autopilot_context(autopilot))
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
        context.update(_social_autopilot_context(autopilot, form=form))
        return render(request, "automation/staff_control.html", context, status=400)

    autopilot = form.save()
    from automation.autopilot import (
        generate_autopilot_calendar,
        reconcile_autopilot_state,
    )

    reconciled = reconcile_autopilot_state(autopilot)
    if autopilot.enabled:
        result = generate_autopilot_calendar()
        created = result.get("created", 0)
        channel_names = ", ".join(
            CHANNEL_LABELS[channel]
            for channel in autopilot.channels
            if channel in CHANNEL_LABELS
        )
        item_label = "draft" if autopilot.mode == autopilot.MODE_CONTROLLED else "scheduled post"
        if created:
            messages.success(
                request,
                (
                    f"Autopilot is ready for {channel_names}. "
                    f"Created {created} {item_label}{'' if created == 1 else 's'} "
                    f"covering the next {autopilot.queue_days} day"
                    f"{'' if autopilot.queue_days == 1 else 's'}."
                ),
            )
        else:
            messages.success(
                request,
                f"Autopilot settings saved for {channel_names}. The existing schedule is already up to date.",
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
    channels = [
        channel for channel in (autopilot.channels or [])
        if channel in CHANNEL_LABELS
    ]
    if not channels:
        messages.warning(
            request, "No social channels are selected. Select and save a channel before testing."
        )
        return redirect("staff_automation_control")
    for channel in channels:
        result = diagnose_channel(channel)
        text = f"{channel.title()}: {result['message']}"
        if result["ok"]:
            messages.success(request, text)
        else:
            messages.error(request, text)
    return redirect("staff_automation_control")


@require_POST
def social_autopilot_publish_now(request, post_id: int):
    _require_automation_staff(request, change=True)
    post = get_object_or_404(ScheduledPost, pk=post_id)
    from automation.autopilot import publish_autopilot_post_now

    result = publish_autopilot_post_now(post, actor=request.user)
    if result.get("error"):
        messages.error(request, result["error"])
    else:
        queued = result.get("queued", 0)
        messages.success(
            request,
            (
                f"Publish now requested. {queued} channel delivery"
                f"{'' if queued == 1 else 'ies'} queued for the worker. "
                "Check the delivery status for confirmation; posting time depends "
                "on worker health and channel availability. Later posts are unchanged."
            ),
        )
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
