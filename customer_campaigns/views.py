from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import StaffRequiredMixin
from customer_campaigns.forms import (
    CampaignApprovalForm,
    CampaignSendForm,
    CustomerCampaignForm,
)
from customer_campaigns.models import CustomerCampaign, CustomerCampaignRecipient
from customer_campaigns.services import (
    CampaignOperationError,
    approve_campaign,
    cancel_campaign,
    prepare_campaign,
    send_campaign_batch,
)


CAMPAIGN_PERMISSION = "marketing.change_marketingcampaign"


class CustomerCampaignStaffMixin(PermissionRequiredMixin, StaffRequiredMixin):
    permission_required = CAMPAIGN_PERMISSION
    raise_exception = True


def _require_campaign_staff(request) -> None:
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    if not request.user.has_perm(CAMPAIGN_PERMISSION):
        raise PermissionDenied


class CustomerCampaignListView(CustomerCampaignStaffMixin, ListView):
    model = CustomerCampaign
    template_name = "customer_campaigns/list.html"
    context_object_name = "campaigns"
    paginate_by = 30

    def get_queryset(self):
        queryset = CustomerCampaign.objects.select_related(
            "created_by",
            "prepared_by",
            "approved_by",
            "marketing_campaign",
        )
        status = (self.request.GET.get("status") or "").strip()
        if status in dict(CustomerCampaign.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status") or ""
        context["status_choices"] = CustomerCampaign.STATUS_CHOICES
        context["send_enabled"] = bool(
            getattr(settings, "CUSTOMER_CAMPAIGN_SEND_ENABLED", False)
        )
        return context


class CustomerCampaignCreateView(CustomerCampaignStaffMixin, CreateView):
    model = CustomerCampaign
    form_class = CustomerCampaignForm
    template_name = "customer_campaigns/form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Customer campaign draft created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff_customer_campaign_detail", kwargs={"pk": self.object.pk})


class CustomerCampaignUpdateView(CustomerCampaignStaffMixin, UpdateView):
    model = CustomerCampaign
    form_class = CustomerCampaignForm
    template_name = "customer_campaigns/form.html"

    def get_queryset(self):
        return CustomerCampaign.objects.filter(status=CustomerCampaign.STATUS_DRAFT)

    def form_valid(self, form):
        messages.success(self.request, "Customer campaign draft updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff_customer_campaign_detail", kwargs={"pk": self.object.pk})


def customer_campaign_detail(request, pk: int):
    _require_campaign_staff(request)
    campaign = get_object_or_404(
        CustomerCampaign.objects.select_related(
            "created_by",
            "prepared_by",
            "approved_by",
            "sent_by",
            "marketing_campaign",
        ),
        pk=pk,
    )
    recipients = campaign.recipients.select_related(
        "customer", "consent_event", "outbound_email"
    ).order_by("status", "customer__name", "id")[:200]
    context = {
        "campaign": campaign,
        "recipients": recipients,
        "approval_form": CampaignApprovalForm(),
        "send_form": CampaignSendForm(campaign=campaign),
        "send_enabled": bool(
            getattr(settings, "CUSTOMER_CAMPAIGN_SEND_ENABLED", False)
        ),
        "separate_approver_required": bool(
            getattr(settings, "CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER", True)
        ),
        "safe_batch_size": int(getattr(settings, "CUSTOMER_CAMPAIGN_BATCH_SIZE", 10)),
        "pending_count": campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_PENDING
        ).count(),
        "processing_count": campaign.recipients.filter(
            status=CustomerCampaignRecipient.STATUS_PROCESSING
        ).count(),
    }
    return render(request, "customer_campaigns/detail.html", context)


@require_POST
def customer_campaign_prepare(request, pk: int):
    _require_campaign_staff(request)
    campaign = get_object_or_404(CustomerCampaign, pk=pk)
    try:
        prepare_campaign(campaign, user=request.user)
    except CampaignOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Audience prepared. A different authorised staff member must review and approve it.",
        )
    return redirect("staff_customer_campaign_detail", pk=campaign.pk)


@require_POST
def customer_campaign_approve(request, pk: int):
    _require_campaign_staff(request)
    campaign = get_object_or_404(CustomerCampaign, pk=pk)
    form = CampaignApprovalForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Confirm the approval review before continuing.")
        return redirect("staff_customer_campaign_detail", pk=campaign.pk)
    try:
        approve_campaign(
            campaign,
            user=request.user,
            approval_note=form.cleaned_data.get("approval_note") or "",
        )
    except CampaignOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Campaign approved. No messages have been sent yet.")
    return redirect("staff_customer_campaign_detail", pk=campaign.pk)


@require_POST
def customer_campaign_send(request, pk: int):
    _require_campaign_staff(request)
    campaign = get_object_or_404(CustomerCampaign, pk=pk)
    form = CampaignSendForm(request.POST, campaign=campaign)
    if not form.is_valid():
        messages.error(request, "The send confirmation was not valid.")
        return redirect("staff_customer_campaign_detail", pk=campaign.pk)
    try:
        campaign = send_campaign_batch(
            campaign,
            user=request.user,
            batch_size=form.cleaned_data.get("batch_size"),
        )
    except CampaignOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            (
                "Batch processed — "
                f"sent: {campaign.sent_count}; "
                f"suppressed: {campaign.suppressed_count}; "
                f"failed: {campaign.failed_count}."
            ),
        )
    return redirect("staff_customer_campaign_detail", pk=campaign.pk)


@require_POST
def customer_campaign_cancel(request, pk: int):
    _require_campaign_staff(request)
    campaign = get_object_or_404(CustomerCampaign, pk=pk)
    try:
        cancel_campaign(campaign, user=request.user)
    except CampaignOperationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Campaign cancelled. Remaining recipients were suppressed.")
    return redirect("staff_customer_campaign_detail", pk=campaign.pk)
