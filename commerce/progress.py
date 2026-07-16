from __future__ import annotations

from commerce.models import Order


DELIVERY_STEPS = [
    (Order.STATUS_PENDING, "Order placed"),
    (Order.STATUS_CONFIRMED, "Confirmed"),
    (Order.STATUS_PROCESSING, "Preparing order"),
    (Order.STATUS_READY, "Ready for dispatch"),
    (Order.STATUS_DISPATCHED, "Dispatched"),
    (Order.STATUS_DELIVERED, "Delivered"),
]

PICKUP_STEPS = [
    (Order.STATUS_PENDING, "Order placed"),
    (Order.STATUS_CONFIRMED, "Confirmed"),
    (Order.STATUS_PROCESSING, "Preparing order"),
    (Order.STATUS_READY, "Ready for pickup"),
    (Order.STATUS_FULFILLED, "Collected / fulfilled"),
]


def order_progress(order: Order) -> dict:
    steps = PICKUP_STEPS if order.fulfillment_type == Order.FULFILLMENT_PICKUP else DELIVERY_STEPS
    status_events = list(order.status_events.all())
    event_dates = {event.to_status: event.created_at for event in status_events}
    event_notes = {event.to_status: event.note for event in status_events if event.note}
    event_dates.setdefault(Order.STATUS_PENDING, order.placed_at)

    if order.status == Order.STATUS_CANCELLED:
        last_status = status_events[-1].from_status if status_events else Order.STATUS_PENDING
        current_index = next(
            (index for index, (status, _label) in enumerate(steps) if status == last_status),
            0,
        )
    elif order.status == Order.STATUS_FULFILLED and order.fulfillment_type == Order.FULFILLMENT_DELIVERY:
        current_index = len(steps) - 1
    else:
        current_index = next(
            (index for index, (status, _label) in enumerate(steps) if status == order.status),
            0,
        )

    rendered = []
    for index, (status, label) in enumerate(steps):
        if order.status == Order.STATUS_CANCELLED:
            state = "complete" if index <= current_index else "upcoming"
        elif index < current_index:
            state = "complete"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        rendered.append(
            {
                "status": status,
                "label": label,
                "state": state,
                "occurred_at": event_dates.get(status),
                "note": event_notes.get(status, ""),
            }
        )

    return {
        "steps": rendered,
        "cancelled": order.status == Order.STATUS_CANCELLED,
        "cancellation_reason": order.cancellation_reason,
        "current_label": order.get_status_display(),
    }
