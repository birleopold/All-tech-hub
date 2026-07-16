from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from commerce.models import Order
from core.audit import log_audit_event
from reliability.models import (
    OrderReservation,
    PaymentAttempt,
    PaymentRefund,
    PaymentWebhookEvent,
)


PAYMENT_TRANSITIONS = {
    PaymentAttempt.STATUS_CREATED: {
        PaymentAttempt.STATUS_PENDING,
        PaymentAttempt.STATUS_AUTHORISED,
        PaymentAttempt.STATUS_PAID,
        PaymentAttempt.STATUS_FAILED,
        PaymentAttempt.STATUS_CANCELLED,
    },
    PaymentAttempt.STATUS_PENDING: {
        PaymentAttempt.STATUS_AUTHORISED,
        PaymentAttempt.STATUS_PAID,
        PaymentAttempt.STATUS_FAILED,
        PaymentAttempt.STATUS_EXPIRED,
        PaymentAttempt.STATUS_CANCELLED,
    },
    PaymentAttempt.STATUS_AUTHORISED: {
        PaymentAttempt.STATUS_PAID,
        PaymentAttempt.STATUS_FAILED,
        PaymentAttempt.STATUS_CANCELLED,
    },
    PaymentAttempt.STATUS_PAID: {
        PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
        PaymentAttempt.STATUS_REFUNDED,
        PaymentAttempt.STATUS_DISPUTED,
    },
    PaymentAttempt.STATUS_PARTIALLY_REFUNDED: {
        PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
        PaymentAttempt.STATUS_REFUNDED,
        PaymentAttempt.STATUS_DISPUTED,
    },
    PaymentAttempt.STATUS_DISPUTED: {
        PaymentAttempt.STATUS_PAID,
        PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
        PaymentAttempt.STATUS_REFUNDED,
    },
    PaymentAttempt.STATUS_FAILED: set(),
    PaymentAttempt.STATUS_EXPIRED: set(),
    PaymentAttempt.STATUS_REFUNDED: set(),
    PaymentAttempt.STATUS_CANCELLED: set(),
}


def reservation_duration() -> timedelta:
    minutes = max(5, int(getattr(settings, "ORDER_RESERVATION_MINUTES", 1440)))
    return timedelta(minutes=minutes)


def order_for_idempotency_key(key: str) -> Order | None:
    key = (key or "").strip()
    if not key:
        return None
    reservation = (
        OrderReservation.objects.select_related("order")
        .filter(idempotency_key=key)
        .first()
    )
    return reservation.order if reservation else None


@transaction.atomic
def create_order_reservation(
    order: Order,
    idempotency_key: str,
    *,
    actor=None,
    expires_at=None,
) -> OrderReservation:
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError("A checkout idempotency key is required.")
    expires_at = expires_at or (timezone.now() + reservation_duration())
    try:
        reservation = OrderReservation.objects.create(
            order=order,
            idempotency_key=key,
            expires_at=expires_at,
            created_by=actor,
        )
    except IntegrityError as exc:
        existing = (
            OrderReservation.objects.select_related("order")
            .filter(idempotency_key=key)
            .first()
        )
        if existing and existing.order_id == order.pk:
            return existing
        raise ValidationError(
            "This checkout request has already been used for another order."
        ) from exc
    log_audit_event(
        actor=actor,
        verb="commerce.stock_reserved",
        summary=(
            f"Stock reserved for {order.reference} until "
            f"{timezone.localtime(expires_at):%Y-%m-%d %H:%M}"
        ),
        target=reservation,
    )
    return reservation


@transaction.atomic
def commit_order_reservation(order: Order, *, actor=None, reason: str = "") -> bool:
    reservation = (
        OrderReservation.objects.select_for_update()
        .filter(order=order)
        .first()
    )
    if reservation is None or reservation.status != OrderReservation.STATUS_RESERVED:
        return False
    reservation.status = OrderReservation.STATUS_COMMITTED
    reservation.committed_at = timezone.now()
    reservation.release_reason = (reason or "Order confirmed")[:255]
    reservation.save(
        update_fields=["status", "committed_at", "release_reason"]
    )
    log_audit_event(
        actor=actor,
        verb="commerce.stock_committed",
        summary=f"Reserved stock committed for {order.reference}",
        target=reservation,
    )
    return True


@transaction.atomic
def close_order_reservation(
    order: Order,
    *,
    actor=None,
    reason: str = "",
    expired: bool = False,
) -> bool:
    reservation = (
        OrderReservation.objects.select_for_update()
        .filter(order=order)
        .first()
    )
    if reservation is None or reservation.status in {
        OrderReservation.STATUS_RELEASED,
        OrderReservation.STATUS_EXPIRED,
    }:
        return False
    reservation.status = (
        OrderReservation.STATUS_EXPIRED
        if expired
        else OrderReservation.STATUS_RELEASED
    )
    reservation.released_at = timezone.now()
    reservation.release_reason = (reason or "Order cancelled")[:255]
    reservation.save(
        update_fields=["status", "released_at", "release_reason"]
    )
    log_audit_event(
        actor=actor,
        verb=(
            "commerce.stock_reservation_expired"
            if expired
            else "commerce.stock_released"
        ),
        summary=(
            f"Reserved stock {'expired' if expired else 'released'} for "
            f"{order.reference}: {reservation.release_reason}"
        ),
        target=reservation,
    )
    return True


def _normalise_money(amount) -> Decimal:
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValidationError("Enter a valid payment amount.") from exc
    if value <= 0:
        raise ValidationError("Payment amount must be positive.")
    return value


@transaction.atomic
def create_payment_attempt(
    *,
    order: Order,
    idempotency_key: str,
    amount,
    provider: str = "manual",
    currency: str = "UGX",
    external_reference: str = "",
    safe_metadata: dict | None = None,
    request_fingerprint: str = "",
    actor=None,
) -> tuple[PaymentAttempt, bool]:
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError("A payment idempotency key is required.")
    normalised_amount = _normalise_money(amount)
    provider = (provider or "manual").strip().lower()[:64]
    currency = (currency or "UGX").strip().upper()[:8]
    existing = PaymentAttempt.objects.select_for_update().filter(
        idempotency_key=key
    ).first()
    if existing:
        if (
            existing.order_id != order.pk
            or existing.amount != normalised_amount
            or existing.provider != provider
            or existing.currency != currency
        ):
            raise ValidationError(
                "The payment idempotency key was already used with different details."
            )
        return existing, False
    attempt = PaymentAttempt.objects.create(
        order=order,
        idempotency_key=key,
        provider=provider,
        external_reference=(external_reference or "")[:160],
        amount=normalised_amount,
        currency=currency,
        safe_metadata=safe_metadata or {},
        request_fingerprint=(request_fingerprint or "")[:64],
    )
    log_audit_event(
        actor=actor,
        verb="billing.payment_attempt_created",
        summary=(
            f"Payment attempt created for {order.reference}: "
            f"{currency} {normalised_amount} via {provider}"
        ),
        target=attempt,
    )
    return attempt, True


@transaction.atomic
def transition_payment_attempt(
    attempt: PaymentAttempt,
    new_status: str,
    *,
    actor=None,
    external_reference: str = "",
    last_error: str = "",
    auto_confirm_order: bool = True,
) -> PaymentAttempt:
    attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(
        pk=attempt.pk
    )
    old_status = attempt.status
    if new_status == old_status:
        return attempt
    if new_status not in PAYMENT_TRANSITIONS.get(old_status, set()):
        raise ValidationError(
            f"Cannot move payment from {attempt.get_status_display()} to "
            f"{dict(PaymentAttempt.STATUS_CHOICES).get(new_status, new_status)}."
        )
    attempt.status = new_status
    if external_reference:
        attempt.external_reference = external_reference[:160]
    attempt.last_error = (last_error or "")[:4000]
    if new_status in {
        PaymentAttempt.STATUS_PAID,
        PaymentAttempt.STATUS_FAILED,
        PaymentAttempt.STATUS_EXPIRED,
        PaymentAttempt.STATUS_REFUNDED,
        PaymentAttempt.STATUS_CANCELLED,
    }:
        attempt.completed_at = timezone.now()
    else:
        attempt.completed_at = None
    attempt.save(
        update_fields=[
            "status",
            "external_reference",
            "last_error",
            "completed_at",
            "updated_at",
        ]
    )
    if new_status == PaymentAttempt.STATUS_PAID:
        commit_order_reservation(
            attempt.order,
            actor=actor,
            reason=f"Payment {attempt.external_reference or attempt.pk} completed",
        )
        if auto_confirm_order and attempt.order.status == Order.STATUS_PENDING:
            from commerce.fulfillment import transition_order

            transition_order(
                attempt.order,
                Order.STATUS_CONFIRMED,
                actor=actor,
                note=f"Payment confirmed via {attempt.provider}",
            )
    log_audit_event(
        actor=actor,
        verb="billing.payment_status_changed",
        summary=(
            f"{attempt.order.reference}: payment {old_status} -> {new_status} "
            f"via {attempt.provider}"
        ),
        target=attempt,
    )
    return attempt


@transaction.atomic
def record_payment_refund(
    *,
    payment_attempt: PaymentAttempt,
    idempotency_key: str,
    amount,
    reason: str,
    external_reference: str = "",
    actor=None,
) -> tuple[PaymentRefund, bool]:
    key = (idempotency_key or "").strip()
    if not key:
        raise ValidationError("A refund idempotency key is required.")
    normalised_amount = _normalise_money(amount)
    payment_attempt = PaymentAttempt.objects.select_for_update().get(
        pk=payment_attempt.pk
    )
    existing = PaymentRefund.objects.filter(idempotency_key=key).first()
    if existing:
        if (
            existing.payment_attempt_id != payment_attempt.pk
            or existing.amount != normalised_amount
        ):
            raise ValidationError(
                "The refund idempotency key was already used with different details."
            )
        return existing, False
    if normalised_amount > payment_attempt.refundable_amount:
        raise ValidationError("Refund exceeds the remaining refundable amount.")
    refund = PaymentRefund.objects.create(
        payment_attempt=payment_attempt,
        idempotency_key=key,
        amount=normalised_amount,
        reason=(reason or "Refund")[:255],
        external_reference=(external_reference or "")[:160],
        processed_by=actor,
    )
    remaining = payment_attempt.refundable_amount
    target_status = (
        PaymentAttempt.STATUS_REFUNDED
        if remaining == Decimal("0")
        else PaymentAttempt.STATUS_PARTIALLY_REFUNDED
    )
    payment_attempt.status = target_status
    payment_attempt.completed_at = (
        timezone.now() if target_status == PaymentAttempt.STATUS_REFUNDED else None
    )
    payment_attempt.save(
        update_fields=["status", "completed_at", "updated_at"]
    )
    log_audit_event(
        actor=actor,
        verb="billing.payment_refunded",
        summary=(
            f"Refunded {payment_attempt.currency} {normalised_amount} for "
            f"{payment_attempt.order.reference}"
        ),
        target=refund,
    )
    return refund, True


def payload_fingerprint(payload) -> str:
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@transaction.atomic
def register_webhook_event(
    *,
    provider: str,
    event_id: str,
    payload,
) -> tuple[PaymentWebhookEvent, bool]:
    provider = (provider or "").strip().lower()[:64]
    event_id = (event_id or "").strip()[:180]
    if not provider or not event_id:
        raise ValidationError("Webhook provider and event ID are required.")
    digest = payload_fingerprint(payload)
    event = PaymentWebhookEvent.objects.select_for_update().filter(
        provider=provider,
        event_id=event_id,
    ).first()
    if event:
        if event.payload_sha256 != digest:
            raise ValidationError(
                "A webhook event ID was reused with a different payload."
            )
        return event, False
    event = PaymentWebhookEvent.objects.create(
        provider=provider,
        event_id=event_id,
        payload_sha256=digest,
    )
    return event, True


@transaction.atomic
def finish_webhook_event(
    event: PaymentWebhookEvent,
    *,
    status: str,
    payment_attempt: PaymentAttempt | None = None,
    error: str = "",
) -> PaymentWebhookEvent:
    valid_statuses = {
        PaymentWebhookEvent.STATUS_PROCESSED,
        PaymentWebhookEvent.STATUS_IGNORED,
        PaymentWebhookEvent.STATUS_FAILED,
    }
    if status not in valid_statuses:
        raise ValidationError("Choose a valid webhook completion status.")
    event = PaymentWebhookEvent.objects.select_for_update().get(pk=event.pk)
    if event.status in {
        PaymentWebhookEvent.STATUS_PROCESSED,
        PaymentWebhookEvent.STATUS_IGNORED,
    }:
        return event
    event.status = status
    event.payment_attempt = payment_attempt
    event.last_error = (error or "")[:4000]
    event.processed_at = timezone.now()
    event.save(
        update_fields=[
            "status",
            "payment_attempt",
            "last_error",
            "processed_at",
        ]
    )
    return event
