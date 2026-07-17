from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.mixins import StaffRequiredMixin
from messaging.deliverability import (
    DeliverabilityError,
    release_suppression,
    upsert_suppression,
)
from messaging.forms import (
    ManualEmailSuppressionForm,
    ReleaseEmailSuppressionForm,
)
from messaging.models import EmailDeliveryEvent, EmailSuppression, OutboundEmail

VIEW_PERMISSION = "messaging.view_emailsuppression"
CHANGE_PERMISSION = "messaging.change_emailsuppression"


class EmailDeliverabilityDashboardView(
    PermissionRequiredMixin,
    StaffRequiredMixin,
    TemplateView,
):
    permission_required = VIEW_PERMISSION
    raise_exception = True
    template_name = "messaging/deliverability_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        stale_minutes = max(
            5,
            min(1440, int(getattr(settings, "EMAIL_STALE_QUEUE_MINUTES", 15))),
        )
        stale_cutoff = now - timedelta(minutes=stale_minutes)
        context.update(
            {
                "status_counts": {
                    row["status"]: row["count"]
                    for row in OutboundEmail.objects.values("status").annotate(
                        count=Count("id")
                    )
                },
                "category_counts": {
                    row["category"]: row["count"]
                    for row in OutboundEmail.objects.values("category").annotate(
                        count=Count("id")
                    )
                },
                "active_suppression_count": EmailSuppression.objects.filter(
                    is_active=True
                ).count(),
                "marketing_suppression_count": EmailSuppression.objects.filter(
                    is_active=True,
                    scope=EmailSuppression.SCOPE_MARKETING,
                ).count(),
                "all_email_suppression_count": EmailSuppression.objects.filter(
                    is_active=True,
                    scope=EmailSuppression.SCOPE_ALL,
                ).count(),
                "recent_suppressions": EmailSuppression.objects.select_related(
                    "created_by", "released_by"
                )[:50],
                "recent_events": EmailDeliveryEvent.objects.select_related(
                    "outbound_email"
                )[:50],
                "recent_emails": OutboundEmail.objects.select_related(
                    "created_by"
                )[:50],
                "stale_queued_count": OutboundEmail.objects.filter(
                    status=OutboundEmail.STATUS_QUEUED,
                    created_at__lt=stale_cutoff,
                ).count(),
                "stale_minutes": stale_minutes,
                "manual_form": ManualEmailSuppressionForm(),
                "can_change_deliverability": self.request.user.has_perm(
                    CHANGE_PERMISSION
                ),
            }
        )
        return context


def _require_staff_permission(request, permission: str):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    if not request.user.has_perm(permission):
        raise PermissionDenied


def email_suppression_detail(request, pk: int):
    _require_staff_permission(request, VIEW_PERMISSION)
    suppression = get_object_or_404(
        EmailSuppression.objects.select_related("created_by", "released_by"),
        pk=pk,
    )
    related_events = EmailDeliveryEvent.objects.filter(
        email_address=suppression.email_address
    ).select_related("outbound_email")[:100]
    related_emails = OutboundEmail.objects.filter(
        normalized_to_email=suppression.email_address
    )[:100]
    return render(
        request,
        "messaging/suppression_detail.html",
        {
            "suppression": suppression,
            "related_events": related_events,
            "related_emails": related_emails,
            "release_form": ReleaseEmailSuppressionForm(
                suppression=suppression
            ),
            "can_change_deliverability": request.user.has_perm(
                CHANGE_PERMISSION
            ),
        },
    )


@require_POST
def email_suppression_add(request):
    _require_staff_permission(request, CHANGE_PERMISSION)
    form = ManualEmailSuppressionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The suppression request was not valid.")
        return redirect("staff_email_deliverability")
    suppression = upsert_suppression(
        email_address=form.cleaned_data["email_address"],
        reason=form.cleaned_data["reason"],
        scope=form.cleaned_data["scope"],
        source=EmailSuppression.SOURCE_STAFF,
        actor=request.user,
        details={"note": form.cleaned_data["note"]},
    )
    messages.success(
        request,
        f"Suppression applied to {suppression.email_address}.",
    )
    return redirect("staff_email_suppression_detail", pk=suppression.pk)


@require_POST
def email_suppression_release(request, pk: int):
    _require_staff_permission(request, CHANGE_PERMISSION)
    suppression = get_object_or_404(EmailSuppression, pk=pk)
    form = ReleaseEmailSuppressionForm(
        request.POST,
        suppression=suppression,
    )
    if not form.is_valid():
        messages.error(request, "The release confirmation was not valid.")
        return redirect("staff_email_suppression_detail", pk=suppression.pk)
    try:
        release_suppression(
            suppression,
            user=request.user,
            reason=form.cleaned_data["release_reason"],
        )
    except DeliverabilityError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Email suppression released after review.")
    return redirect("staff_email_suppression_detail", pk=suppression.pk)
