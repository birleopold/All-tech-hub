from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from commerce.models import Order, OrderStatusEvent
from core.models import CompanySettings
from messaging.models import OutboundEmail


ORDER_SUBJECT_PREFIX = "Order"
REVIEW_SUBJECT_PREFIX = "Review your order"
CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


def _enabled(setting_name: str, default: bool = True) -> bool:
    return bool(getattr(settings, setting_name, default))


def customer_email_delivery_ready() -> bool:
    """The console backend prints mail but does not deliver it to customers."""

    return str(getattr(settings, "EMAIL_BACKEND", "")).strip() != CONSOLE_EMAIL_BACKEND


def _absolute_order_url(order: Order) -> str:
    company = CompanySettings.load()
    base = (company.website or "https://leosoftug.com").rstrip("/") + "/"
    return urljoin(base, order.get_absolute_url().lstrip("/"))


def _deliver(
    *,
    to_email: str,
    subject: str,
    body: str,
    idempotency_key: str,
) -> OutboundEmail | None:
    """Deliver one retry-safe transactional message.

    The automation worker may execute a job more than once after a stale lock or
    network failure. The stable idempotency key makes normal retries reuse one
    outbound record and avoids duplicate sends after a recorded success. SMTP
    itself cannot promise exactly-once delivery if a process dies after provider
    acceptance but before the database status update.
    """

    recipient = (to_email or "").strip().lower()
    if not recipient:
        return None
    if not customer_email_delivery_ready():
        raise RuntimeError(
            "Customer email delivery is unavailable while the Django console mail backend is active."
        )

    key = (idempotency_key or "").strip()[:180]
    if not key:
        raise ValueError("A transactional email idempotency key is required.")

    with transaction.atomic():
        row, _created = OutboundEmail.objects.select_for_update().get_or_create(
            idempotency_key=key,
            defaults={
                "to_email": recipient,
                "normalized_to_email": recipient,
                "category": OutboundEmail.CATEGORY_TRANSACTIONAL,
                "subject": subject[:200],
                "body": body,
                "status": OutboundEmail.STATUS_QUEUED,
            },
        )
        if row.status in {
            OutboundEmail.STATUS_SENT,
            OutboundEmail.STATUS_DELIVERED,
            OutboundEmail.STATUS_SUPPRESSED,
            OutboundEmail.STATUS_BOUNCED,
            OutboundEmail.STATUS_COMPLAINED,
        }:
            return row
        row.to_email = recipient
        row.normalized_to_email = recipient
        row.category = OutboundEmail.CATEGORY_TRANSACTIONAL
        row.subject = subject[:200]
        row.body = body
        row.status = OutboundEmail.STATUS_QUEUED
        row.error = ""
        row.attempt_count += 1
        row.last_attempt_at = timezone.now()
        row.save(
            update_fields=[
                "to_email",
                "normalized_to_email",
                "category",
                "subject",
                "body",
                "status",
                "error",
                "attempt_count",
                "last_attempt_at",
                "updated_at",
            ]
        )

    try:
        send_mail(
            row.subject,
            row.body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception as exc:
        row.mark_failed(str(exc)[:2000])
        row.save(
            update_fields=[
                "status",
                "sent_at",
                "error",
                "last_event_at",
                "updated_at",
            ]
        )
        raise

    row.mark_sent()
    row.save(
        update_fields=[
            "status",
            "sent_at",
            "accepted_at",
            "last_event_at",
            "error",
            "suppression_reason",
            "updated_at",
        ]
    )
    return row


def order_confirmation_subject(order: Order) -> str:
    company = CompanySettings.load()
    return f"Order {order.reference} received — {company.company_name}"


def order_status_subject(order: Order, status_label: str) -> str:
    return f"Order {order.reference}: {status_label}"


def send_order_confirmation(order: Order) -> OutboundEmail | None:
    if not _enabled("ORDER_CUSTOMER_EMAILS_ENABLED", True):
        return None
    order = Order.objects.select_related("customer").prefetch_related(
        "lines__product_variant"
    ).get(pk=order.pk)
    company = CompanySettings.load()
    lines = "\n".join(
        f"- {line.quantity} × {line.description} — {company.currency_code} "
        f"{line.line_total:.2f}"
        for line in order.lines.all()
    )
    payment_guidance = ""
    if company.bank_details.strip():
        payment_guidance = (
            "\nPayment guidance\n"
            "-----------------\n"
            f"{company.bank_details.strip()}\n\n"
            f"Use {order.reference} as the payment reference and keep your transaction proof. "
            "Payment is confirmed only after LEOSOFT verifies it.\n"
        )
    contact = ""
    if company.phone or company.email:
        contact = (
            "\nNeed help? "
            + " · ".join(value for value in [company.phone, company.email] if value)
            + "\n"
        )
    body = (
        f"Hello {order.contact_name},\n\n"
        f"We received your order {order.reference}.\n\n"
        f"{lines}\n\n"
        f"Order total: {company.currency_code} {order.total:.2f}\n"
        f"Fulfilment: {order.get_fulfillment_type_display()}\n"
        f"Current status: {order.get_status_display()}\n"
        f"{payment_guidance}\n"
        f"Track your order securely: {_absolute_order_url(order)}\n"
        f"{contact}\n"
        "Do not forward the private tracking link. It provides access to this order summary.\n\n"
        f"Regards,\n{company.company_name}"
    )
    return _deliver(
        to_email=order.contact_email,
        subject=order_confirmation_subject(order),
        body=body,
        idempotency_key=f"order-confirmation:{order.pk}",
    )


def deliver_order_confirmation_by_id(order_id: int) -> OutboundEmail | None:
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return None
    return send_order_confirmation(order)


def queue_order_confirmation_by_id(order_id: int) -> bool:
    from automation.order_notifications import queue_order_confirmation_email

    return queue_order_confirmation_email(order_id)


def send_order_confirmation_by_id(order_id: int) -> bool:
    """Backward-compatible entry point that now queues durable delivery."""

    return queue_order_confirmation_by_id(order_id)


def send_order_status_update(event: OrderStatusEvent) -> OutboundEmail | None:
    if not _enabled("ORDER_CUSTOMER_EMAILS_ENABLED", True) or not _enabled(
        "ORDER_STATUS_EMAILS_ENABLED", True
    ):
        return None
    if not event.visible_to_customer:
        return None
    event = OrderStatusEvent.objects.select_related("order").get(pk=event.pk)
    order = event.order
    company = CompanySettings.load()
    status_label = event.get_to_status_display()
    note = f"\nUpdate from the team: {event.note}\n" if event.note else ""
    body = (
        f"Hello {order.contact_name},\n\n"
        f"Your order {order.reference} is now: {status_label}.\n"
        f"{note}\n"
        f"Track the latest progress: {_absolute_order_url(order)}\n\n"
        "The tracking link is private. Please do not forward it.\n\n"
        f"Regards,\n{company.company_name}"
    )
    return _deliver(
        to_email=order.contact_email,
        subject=order_status_subject(order, status_label),
        body=body,
        idempotency_key=f"order-status:{event.pk}",
    )


def deliver_order_status_update_by_id(event_id: int) -> OutboundEmail | None:
    try:
        event = OrderStatusEvent.objects.get(pk=event_id)
    except OrderStatusEvent.DoesNotExist:
        return None
    return send_order_status_update(event)


def queue_order_status_update_by_id(event_id: int) -> bool:
    from automation.order_notifications import queue_order_status_email

    return queue_order_status_email(event_id)


def send_order_status_update_by_id(event_id: int) -> bool:
    """Backward-compatible entry point that now queues durable delivery."""

    return queue_order_status_update_by_id(event_id)


def retry_failed_order_emails(*, limit: int = 100) -> dict[str, int]:
    if not customer_email_delivery_ready():
        raise RuntimeError(
            "Customer email delivery is unavailable while the Django console mail backend is active."
        )
    rows = list(
        OutboundEmail.objects.filter(status=OutboundEmail.STATUS_FAILED)
        .filter(
            Q(subject__startswith=f"{ORDER_SUBJECT_PREFIX} ")
            | Q(subject__startswith=f"{REVIEW_SUBJECT_PREFIX} ")
        )
        .order_by("created_at")[: max(1, min(limit, 500))]
    )
    sent = failed = 0
    for row in rows:
        try:
            row.attempt_count += 1
            row.last_attempt_at = timezone.now()
            send_mail(
                row.subject,
                row.body,
                settings.DEFAULT_FROM_EMAIL,
                [row.to_email],
                fail_silently=False,
            )
            row.mark_sent()
            row.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "accepted_at",
                    "last_event_at",
                    "error",
                    "suppression_reason",
                    "attempt_count",
                    "last_attempt_at",
                    "updated_at",
                ]
            )
            sent += 1
        except Exception as exc:
            row.mark_failed(str(exc)[:2000])
            row.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "error",
                    "last_event_at",
                    "attempt_count",
                    "last_attempt_at",
                    "updated_at",
                ]
            )
            failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed}
