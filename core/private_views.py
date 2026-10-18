"""Authorised views for sensitive uploaded files."""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from core.models import TicketComment
from core.private_files import protected_file_response
from operations.models import JobAttachment, JobCard, JobHandover


def _portal_customer(request):
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "customer_profile", None)


def staff_ticket_attachment(request, pk: int):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    comment = get_object_or_404(TicketComment.objects.select_related("ticket"), pk=pk)
    return protected_file_response(comment.attachment, inline=True)


def portal_ticket_attachment(request, pk: int):
    customer = _portal_customer(request)
    if customer is None:
        return redirect("portal_login")
    comment = get_object_or_404(
        TicketComment.objects.select_related("ticket"),
        pk=pk,
        ticket__customer=customer,
        is_internal=False,
    )
    return protected_file_response(comment.attachment, inline=True)


def staff_job_attachment(request, pk: int):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    attachment = get_object_or_404(JobAttachment, pk=pk)
    return protected_file_response(attachment.image, inline=True)


def portal_job_attachment(request, pk: int):
    customer = _portal_customer(request)
    if customer is None:
        return redirect("portal_login")
    attachment = get_object_or_404(
        JobAttachment.objects.select_related("job"),
        pk=pk,
        job__customer=customer,
        show_to_customer=True,
    )
    return protected_file_response(attachment.image, inline=True)


def staff_job_signature(request, pk: int):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    return protected_file_response(job.customer_signature, inline=True)


def staff_job_handover_signature(request, pk: int):
    # A generic staff login is insufficient for a stored customer signature.
    # Technicians, authorised inventory operators and managers have the job
    # permissions assigned by bootstrap_roles; unrelated staff roles do not.
    if (
        not request.user.is_authenticated
        or not request.user.is_staff
        or not (
            request.user.has_perm("operations.view_jobcard")
            or request.user.has_perm("operations.change_jobcard")
        )
    ):
        raise Http404
    handover = get_object_or_404(JobHandover, job_id=pk)
    return protected_file_response(handover.signature, inline=True)


def portal_job_handover_signature(request, pk: int):
    customer = _portal_customer(request)
    if customer is None:
        return redirect("portal_login")
    handover = get_object_or_404(
        JobHandover.objects.select_related("job"), job_id=pk,
        job__customer=customer,
    )
    return protected_file_response(handover.signature, inline=True)
