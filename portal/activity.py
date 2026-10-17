"""One customer-scoped feed from existing order, repair, invoice and ticket records.

No copied customer profiles or persisted shadow activity table: a new record is
immediately visible once its source record is saved.
"""
from billing.models import CommercialDocument
from commerce.models import Order, OrderStatusEvent
from core.models import SupportTicket, TicketComment
from operations.models import JobCard, JobStatusEvent
from django.urls import reverse


def customer_service_activity(customer, limit=10):
    if customer is None:
        return []
    entries = []

    def add(created_at, label, detail, url, kind):
        if created_at is not None:
            entries.append({
                "at": created_at,
                "label": label,
                "detail": detail,
                "url": url,
                "kind": kind,
            })

    orders = Order.objects.filter(customer=customer).order_by("-placed_at")[:5]
    for order in orders:
        add(
            order.placed_at, f"Order {order.reference}",
            order.get_status_display(),
            reverse("portal_order_detail", args=[order.pk]), "order",
        )

    order_events = (
        OrderStatusEvent.objects.filter(
            order__customer=customer, visible_to_customer=True
        ).select_related("order").order_by("-created_at")[:6]
    )
    for event in order_events:
        add(
            event.created_at, f"Order {event.order.reference} updated",
            event.get_to_status_display(),
            reverse("portal_order_detail", args=[event.order_id]), "order",
        )

    jobs = JobCard.objects.filter(customer=customer).order_by("-received_on")[:5]
    for job in jobs:
        add(
            job.received_on, f"Repair {job.number}",
            job.get_status_display(),
            reverse("portal_job_detail", args=[job.pk]), "repair",
        )
    job_events = (
        JobStatusEvent.objects.filter(job__customer=customer)
        .select_related("job").order_by("-created_at")[:6]
    )
    for event in job_events:
        # Job status is customer-facing; internal job notes are not copied.
        label = dict(JobCard.STATUS_CHOICES).get(event.to_status, "Status updated")
        add(
            event.created_at, f"Repair {event.job.number} updated", label,
            reverse("portal_job_detail", args=[event.job_id]), "repair",
        )

    tickets = SupportTicket.objects.filter(customer=customer).order_by("-created_at")[:5]
    for ticket in tickets:
        add(
            ticket.created_at, f"Support {ticket.reference}",
            ticket.get_status_display(),
            reverse("portal_ticket_detail", args=[ticket.pk]), "support",
        )
    replies = (
        TicketComment.objects.filter(ticket__customer=customer, is_internal=False)
        .select_related("ticket").order_by("-created_at")[:6]
    )
    for reply in replies:
        add(
            reply.created_at, f"Reply on {reply.ticket.reference}",
            "New message in your support conversation",
            reverse("portal_ticket_detail", args=[reply.ticket_id]), "support",
        )

    documents = (
        CommercialDocument.objects.filter(customer=customer)
        .exclude(status=CommercialDocument.STATUS_DRAFT)
        .order_by("-created_at")[:5]
    )
    for document in documents:
        add(
            document.created_at, f"Document {document.number}",
            document.get_status_display(),
            reverse("portal_document_pdf", args=[document.pk]), "document",
        )

    return sorted(
        entries,
        key=lambda item: (item["at"], item["kind"], item["label"]),
        reverse=True,
    )[:limit]
