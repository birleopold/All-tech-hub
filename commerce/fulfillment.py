from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from commerce.models import Order, OrderStatusEvent, OrderStockRestoration
from core.audit import log_audit_event
from inventory.models import StockMovement
from inventory.services import change_stock

ALLOWED_TRANSITIONS = {
    Order.STATUS_PENDING: {Order.STATUS_CONFIRMED, Order.STATUS_CANCELLED},
    Order.STATUS_CONFIRMED: {Order.STATUS_PROCESSING, Order.STATUS_CANCELLED},
    Order.STATUS_PROCESSING: {Order.STATUS_READY, Order.STATUS_CANCELLED},
    Order.STATUS_READY: {
        Order.STATUS_DISPATCHED,
        Order.STATUS_FULFILLED,
        Order.STATUS_CANCELLED,
    },
    Order.STATUS_DISPATCHED: {Order.STATUS_DELIVERED},
    Order.STATUS_DELIVERED: set(),
    Order.STATUS_FULFILLED: set(),
    Order.STATUS_CANCELLED: set(),
}


@transaction.atomic
def restore_cancelled_order_stock(order: Order, actor=None) -> bool:
    order = Order.objects.select_for_update().prefetch_related(
        "lines__product", "lines__product_variant", "lines__returns"
    ).get(pk=order.pk)
    if hasattr(order, "stock_restoration"):
        return False
    if any(line.returns.exists() for line in order.lines.all()):
        raise ValidationError(
            "Orders with recorded returns cannot be cancelled automatically."
        )
    for line in order.lines.all():
        if line.product is None or line.product.kind != line.product.KIND_PHYSICAL:
            continue
        if line.product_variant and not line.product_variant.track_inventory:
            continue
        if not line.product_variant and not line.product.track_inventory:
            continue
        change_stock(
            product=line.product,
            product_variant=line.product_variant,
            quantity_delta=line.quantity,
            movement_type=StockMovement.TYPE_CANCELLATION,
            reference=f"{order.reference}-CANCEL",
            note="Automatic stock restoration after cancellation",
            actor=actor,
        )
    restoration = OrderStockRestoration.objects.create(order=order, restored_by=actor)
    log_audit_event(
        actor=actor,
        verb="commerce.stock_restored",
        summary=f"Stock restored once for cancelled order {order.reference}",
        target=restoration,
    )
    return True


@transaction.atomic
def transition_order(order: Order, new_status: str, actor=None, note: str = ""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    old_status = order.status
    if new_status == old_status:
        return order
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise ValidationError(
            f"Cannot move order from {order.get_status_display()} to "
            f"{dict(Order.STATUS_CHOICES).get(new_status, new_status)}."
        )

    if new_status == Order.STATUS_CANCELLED:
        cancellation_reason = (note or "").strip()
        if not cancellation_reason:
            raise ValidationError("A cancellation reason is required.")
        from reliability.order_payments import (
            cancel_open_payment_attempts,
            has_unsettled_successful_payment,
        )

        if has_unsettled_successful_payment(order):
            raise ValidationError(
                "This order has a successful payment that is not fully refunded. "
                "Record the refund before cancelling the order."
            )
        restore_cancelled_order_stock(order, actor=actor)
        cancel_open_payment_attempts(
            order,
            actor=actor,
            reason=cancellation_reason,
        )
        order.cancellation_reason = cancellation_reason[:255]
        order.cancelled_at = timezone.now()
        from reliability.services import close_order_reservation

        close_order_reservation(
            order,
            actor=actor,
            reason=cancellation_reason,
            expired=cancellation_reason.lower().startswith("reservation expired"),
        )
    elif new_status in {
        Order.STATUS_CONFIRMED,
        Order.STATUS_PROCESSING,
        Order.STATUS_READY,
        Order.STATUS_DISPATCHED,
        Order.STATUS_DELIVERED,
        Order.STATUS_FULFILLED,
    }:
        from reliability.services import commit_order_reservation

        commit_order_reservation(
            order,
            actor=actor,
            reason=note or f"Order moved to {new_status}",
        )

    if new_status in {Order.STATUS_DELIVERED, Order.STATUS_FULFILLED}:
        order.fulfilled_at = timezone.now()
    order.status = new_status
    order.save(
        update_fields=[
            "status",
            "cancellation_reason",
            "cancelled_at",
            "fulfilled_at",
            "updated_at",
        ]
    )
    event = OrderStatusEvent.objects.create(
        order=order,
        from_status=old_status,
        to_status=new_status,
        note=note[:255],
        changed_by=actor,
    )
    log_audit_event(
        actor=actor,
        verb="commerce.order_status_changed",
        summary=f"{order.reference}: {old_status} -> {new_status}",
        target=event,
    )
    return order
