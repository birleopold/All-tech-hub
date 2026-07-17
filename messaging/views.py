from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from billing.models import CommercialDocument
from billing.pdf import render_commercial_pdf
from core.mixins import StaffRequiredMixin
from messaging.deliverability import active_suppression
from messaging.forms import RetryOutboundEmailForm, SendEmailForm
from messaging.models import OutboundEmail
from messaging.utils import retry_outbound_email, send_outbound_email
from operations.models import JobCard
from operations.pdf import render_jobcard_pdf


def email_document(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(CommercialDocument, pk=pk)
    initial = {
        "to_email": doc.display_customer_email,
        "subject": f"{doc.get_doc_type_display()} {doc.number}",
        "body": f"Hello {doc.display_customer_name},\n\nPlease find attached: {doc.get_doc_type_display()} {doc.number}.\n\nRegards,\n",
        "attach_pdf": True,
    }
    if request.method == "POST":
        form = SendEmailForm(request.POST)
        if form.is_valid():
            attach = form.cleaned_data["attach_pdf"]
            attachment_bytes = render_commercial_pdf(doc) if attach else None
            attachment_name = f"{doc.number}.pdf" if attach else None
            log = send_outbound_email(
                to_email=form.cleaned_data["to_email"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data.get("body") or "",
                created_by=request.user,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
                commercial_document=doc,
            )
            if log.status in {
                OutboundEmail.STATUS_SENT,
                OutboundEmail.STATUS_DELIVERED,
            }:
                messages.success(request, "Email accepted by the delivery service.")
            elif log.status == OutboundEmail.STATUS_SUPPRESSED:
                messages.error(
                    request,
                    "Email was not sent because the address is actively suppressed.",
                )
            else:
                messages.error(request, f"Email failed: {log.error}")
            return redirect("staff_document_view", pk=doc.pk)
    else:
        form = SendEmailForm(initial=initial)
    return render(
        request,
        "messaging/send_email.html",
        {"form": form, "title": f"Email {doc.number}"},
    )


def email_jobcard(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    initial = {
        "to_email": job.customer.email,
        "subject": f"Job card {job.number}: {job.title}",
        "body": f"Hello {job.customer.name},\n\nAttached is your job card {job.number}.\nStatus: {job.get_status_display()}.\n\nRegards,\n",
        "attach_pdf": True,
    }
    if request.method == "POST":
        form = SendEmailForm(request.POST)
        if form.is_valid():
            attach = form.cleaned_data["attach_pdf"]
            attachment_bytes = render_jobcard_pdf(job) if attach else None
            attachment_name = f"{job.number}.pdf" if attach else None
            log = send_outbound_email(
                to_email=form.cleaned_data["to_email"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data.get("body") or "",
                created_by=request.user,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
                job_card=job,
            )
            if log.status in {
                OutboundEmail.STATUS_SENT,
                OutboundEmail.STATUS_DELIVERED,
            }:
                messages.success(request, "Email accepted by the delivery service.")
            elif log.status == OutboundEmail.STATUS_SUPPRESSED:
                messages.error(
                    request,
                    "Email was not sent because the address is actively suppressed.",
                )
            else:
                messages.error(request, f"Email failed: {log.error}")
            return redirect("staff_job_detail", pk=job.pk)
    else:
        form = SendEmailForm(initial=initial)
    return render(
        request,
        "messaging/send_email.html",
        {"form": form, "title": f"Email {job.number}"},
    )


def email_job_update(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    latest_public = job.notes.filter(is_internal=False).order_by("-created_at").first()
    update_text = latest_public.body if latest_public else ""
    initial = {
        "to_email": job.customer.email,
        "subject": f"Update — Job {job.number}: {job.title}",
        "body": (
            f"Hello {job.customer.name},\n\n"
            f"Job: {job.number} — {job.title}\n"
            f"Status: {job.get_status_display()}\n"
            + (f"\nUpdate:\n{update_text}\n" if update_text else "\n")
            + "\nRegards,\n"
        ),
        "attach_pdf": False,
    }
    if request.method == "POST":
        form = SendEmailForm(request.POST)
        if form.is_valid():
            attach = form.cleaned_data["attach_pdf"]
            attachment_bytes = render_jobcard_pdf(job) if attach else None
            attachment_name = f"{job.number}.pdf" if attach else None
            log = send_outbound_email(
                to_email=form.cleaned_data["to_email"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data.get("body") or "",
                created_by=request.user,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
                job_card=job,
            )
            if log.status in {
                OutboundEmail.STATUS_SENT,
                OutboundEmail.STATUS_DELIVERED,
            }:
                messages.success(request, "Update accepted by the delivery service.")
            elif log.status == OutboundEmail.STATUS_SUPPRESSED:
                messages.error(
                    request,
                    "Update was not sent because the address is actively suppressed.",
                )
            else:
                messages.error(request, f"Email failed: {log.error}")
            return redirect("staff_job_detail", pk=job.pk)
    else:
        form = SendEmailForm(initial=initial)
    return render(
        request,
        "messaging/send_email.html",
        {"form": form, "title": f"Email update — {job.number}"},
    )


class EmailLogListView(StaffRequiredMixin, ListView):
    template_name = "messaging/email_log_list.html"
    context_object_name = "emails"
    paginate_by = 30

    def get_queryset(self):
        queryset = OutboundEmail.objects.select_related(
            "created_by", "commercial_document", "job_card"
        ).order_by("-created_at", "-id")
        status = self.request.GET.get("status")
        if status in dict(OutboundEmail.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        category = self.request.GET.get("category")
        if category in dict(OutboundEmail.CATEGORY_CHOICES):
            queryset = queryset.filter(category=category)
        query = self.request.GET.get("q")
        if query:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(to_email__icontains=query) | Q(subject__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = OutboundEmail.STATUS_CHOICES
        context["category_choices"] = OutboundEmail.CATEGORY_CHOICES
        context["status"] = self.request.GET.get("status") or ""
        context["category"] = self.request.GET.get("category") or ""
        context["q"] = self.request.GET.get("q") or ""
        return context


def email_log_detail(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    email = get_object_or_404(
        OutboundEmail.objects.select_related(
            "created_by", "commercial_document", "job_card"
        ),
        pk=pk,
    )
    suppression = active_suppression(email.normalized_to_email, email.category)
    return render(
        request,
        "messaging/email_log_detail.html",
        {
            "email": email,
            "events": email.delivery_events.all()[:100],
            "active_suppression": suppression,
            "retry_form": RetryOutboundEmailForm(outbound_email=email),
            "can_retry_email": (
                request.user.has_perm("messaging.change_outboundemail")
                and email.can_retry
                and suppression is None
            ),
        },
    )


def email_log_retry(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    if not request.user.has_perm("messaging.change_outboundemail"):
        raise PermissionDenied
    if request.method != "POST":
        return redirect("staff_email_log_detail", pk=pk)
    log = get_object_or_404(
        OutboundEmail.objects.select_related("commercial_document", "job_card"),
        pk=pk,
    )
    campaign_recipient = log.customer_campaign_recipients.select_related(
        "campaign"
    ).first()
    if campaign_recipient is not None:
        messages.error(
            request,
            (
                "Controlled campaign emails cannot be retried from the generic email log. "
                "Review the campaign recipient and current consent instead."
            ),
        )
        return redirect(
            "staff_customer_campaign_detail",
            pk=campaign_recipient.campaign_id,
        )
    form = RetryOutboundEmailForm(request.POST, outbound_email=log)
    if not form.is_valid():
        messages.error(request, "The retry confirmation was not valid.")
        return redirect("staff_email_log_detail", pk=pk)
    if not log.can_retry:
        messages.error(request, "This email state is not eligible for retry.")
        return redirect("staff_email_log_detail", pk=pk)
    suppression = active_suppression(log.normalized_to_email, log.category)
    if suppression:
        messages.error(
            request,
            "The active address suppression must be reviewed before retry.",
        )
        return redirect("staff_email_log_detail", pk=pk)

    attachment_name = None
    attachment_bytes = None
    if log.commercial_document_id:
        attachment_name = f"{log.commercial_document.number}.pdf"
        attachment_bytes = render_commercial_pdf(log.commercial_document)
    elif log.job_card_id:
        attachment_name = f"{log.job_card.number}.pdf"
        attachment_bytes = render_jobcard_pdf(log.job_card)
    retry_outbound_email(
        log,
        attachment_name=attachment_name,
        attachment_bytes=attachment_bytes,
    )
    log.refresh_from_db()
    if log.status in {
        OutboundEmail.STATUS_SENT,
        OutboundEmail.STATUS_DELIVERED,
    }:
        messages.success(request, "Email accepted by the delivery service.")
    elif log.status == OutboundEmail.STATUS_SUPPRESSED:
        messages.error(request, "Retry was suppressed by the address controls.")
    else:
        messages.error(request, f"Retry failed: {log.error}")
    return redirect("staff_email_log_detail", pk=pk)
