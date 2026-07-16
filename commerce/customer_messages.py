from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from commerce.models import Order, OrderStatusEvent
from core.models import CompanySettings
from messaging.models import OutboundEmail


ORDER_SUBJECT_PREFIX = "Order"
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


def _deliver(*, to_email: str, subject: str, body: str) -> OutboundEmail | None:
    recipient = (to_email or "").strip().lower()
    if not recipient or not customer_email_delivery_ready():
        return None

    existing = OutboundEmail.objects.filter(
        to_email__iexact=recipient,
        subject=subject,
        status__in=[OutboundEmail.STATUS_QUEUED, OutboundEmail.STATUS_SENT],
    ).first()
    if existing:
        return existing

    row = OutboundEmail.objects.create(
        to_email=recipient,
        subject=subject[:200],
        body=body,
        status=OutboundEmail.STATUS_QUEUED,
    )
    try:
        send_mail(
            row.subject,
            row.body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        row.mark_sent()
        row.error = ""
        row.save(update_fields=["status", "sent_at", "error"])
    except Exception as exc:  # Delivery must never break checkout or status changes.
        row.mark_failed(str(exc)[:2000])
        row.save(update_fields=["status", "sent_at", "error"])
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
    )


def send_order_confirmation_by_id(order_id: int) -> OutboundEmail | None:
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return None
    return send_order_confirmation(order)


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
    )


def send_order_status_update_by_id(event_id: int) -> OutboundEmail | None:
    try:
        event = OrderStatusEvent.objects.get(pk=event_id)
    except OrderStatusEvent.DoesNotExist:
        return None
    return send_order_status_update(event)


def retry_failed_order_emails(*, limit: int = 100) -> dict[str, int]:
    if not customer_email_delivery_ready():
        raise RuntimeError(
            "Customer email delivery is unavailable while the Django console mail backend is active."
        )
    rows = list(
        OutboundEmail.objects.filter(
            status=OutboundEmail.STATUS_FAILED,
            subject__startswith=f"{ORDER_SUBJECT_PREFIX} ",
        ).order_by("created_at")[: max(1, min(limit, 500))]
    )
    sent = failed = 0
    for row in rows:
        try:
            send_mail(
                row.subject,
                row.body,
                settings.DEFAULT_FROM_EMAIL,
                [row.to_email],
                fail_silently=False,
            )
            row.status = OutboundEmail.STATUS_SENT
            row.sent_at = timezone.now()
            row.error = ""
            row.save(update_fields=["status", "sent_at", "error"])
            sent += 1
        except Exception as exc:
            row.error = str(exc)[:2000]
            row.sent_at = timezone.now()
            row.save(update_fields=["error", "sent_at"])
            failed += 1
    return {"processed": len(rows), "sent": sent, "failed": failed}
