from django.conf import settings
from django.core.mail import send_mail


def notify_order_status(order) -> None:
    if not order.contact_email:
        return
    shipment = getattr(order, "shipment", None)
    lines = [
        f"Your order {order.reference} is now {order.get_status_display()}.",
    ]
    if shipment and shipment.tracking_number:
        lines.append(f"Tracking number: {shipment.tracking_number}")
    if shipment and shipment.tracking_url:
        lines.append(f"Tracking link: {shipment.tracking_url}")
    if shipment and shipment.estimated_delivery:
        lines.append(f"Estimated delivery: {shipment.estimated_delivery}")
    lines.append("Sign in to your customer portal for the full timeline.")
    send_mail(
        f"[ALLTECH] Order update: {order.reference}",
        "\n\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [order.contact_email],
        fail_silently=True,
    )
