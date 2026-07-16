from django.db import transaction

from commerce.models import Order
from reliability.models import PaymentAttempt
from reliability.services import transition_payment_attempt


OPEN_PAYMENT_STATUSES = {
    PaymentAttempt.STATUS_CREATED,
    PaymentAttempt.STATUS_PENDING,
    PaymentAttempt.STATUS_AUTHORISED,
}

UNSETTLED_SUCCESS_STATUSES = {
    PaymentAttempt.STATUS_PAID,
    PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
    PaymentAttempt.STATUS_DISPUTED,
}


def has_unsettled_successful_payment(order: Order) -> bool:
    return order.payment_attempts.filter(
        status__in=UNSETTLED_SUCCESS_STATUSES
    ).exists()


@transaction.atomic
def cancel_open_payment_attempts(
    order: Order,
    *,
    actor=None,
    reason: str = "Order cancelled",
) -> int:
    attempts = list(
        PaymentAttempt.objects.select_for_update()
        .filter(order=order, status__in=OPEN_PAYMENT_STATUSES)
        .order_by("id")
    )
    for attempt in attempts:
        transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_CANCELLED,
            actor=actor,
            last_error=reason,
            auto_confirm_order=False,
        )
    return len(attempts)
