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

COUNTED_PAYMENT_STATUSES = {
    PaymentAttempt.STATUS_PAID,
    PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
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
    reservation, created = OrderReservation.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "order": order,
            "expires_at": expires_at,
            "created_by": actor,
        },
    )
    if reservation.order_id != order.pk:
        raise ValidationError(
            "This checkout request has already been used for another order."
        )
    if created:
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


def _attempt_net_amount(attempt: PaymentAttempt) -> Decimal:
    refunded = sum(
        (refund.amount for refund in attempt.refunds.all()),
        Decimal("0"),
    )
    return max(Decimal("0"), attempt.amount - refunded).quantize(Decimal("0.01"))


def _net_paid_total(
    order: Order,
    *,
    exclude_attempt_id: int | None = None,
    lock_attempts: bool = False,
) -> Decimal:
    attempts = PaymentAttempt.objects.filter(
        order=order,
        status__in=COUNTED_PAYMENT_STATUSES,
    )
    if exclude_attempt_id is not None:
        attempts = attempts.exclude(pk=exclude_attempt_id)
    if lock_attempts:
        attempts = attempts.select_for_update()
    attempts = attempts.prefetch_related("refunds").order_by("id")
    return sum(
        (_attempt_net_amount(attempt) for attempt in attempts),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


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
    external_reference = (external_reference or "").strip()[:160]
    locked_order = Order.objects.select_for_update().get(pk=order.pk)

    if external_reference:
        provider_existing = PaymentAttempt.objects.filter(
            provider=provider,
            external_reference=external_reference,
        ).first()
        if provider_existing:
            if (
                provider_existing.order_id != locked_order.pk
                or provider_existing.amount != normalised_amount
                or provider_existing.currency != currency
            ):
                raise ValidationError(
                    "This provider payment reference is already linked to different details."
                )
            return provider_existing, False

    try:
        attempt, created = PaymentAttempt.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "order": locked_order,
                "provider": provider,
                "external_reference": external_reference,
                "amount": normalised_amount,
                "currency": currency,
                "safe_metadata": safe_metadata or {},
                "request_fingerprint": (request_fingerprint or "")[:64],
            },
        )
    except IntegrityError as exc:
        provider_existing = None
        if external_reference:
            provider_existing = PaymentAttempt.objects.filter(
                provider=provider,
                external_reference=external_reference,
            ).first()
        if provider_existing and (
            provider_existing.order_id == locked_order.pk
            and provider_existing.amount == normalised_amount
            and provider_existing.currency == currency
        ):
            return provider_existing, False
        raise ValidationError(
            "This payment request conflicts with an existing provider transaction."
        ) from exc

    if (
        attempt.order_id != locked_order.pk
        or attempt.amount != normalised_amount
        or attempt.provider != provider
        or attempt.currency != currency
        or (
            external_reference
            and attempt.external_reference != external_reference
        )
    ):
        raise ValidationError(
            "The payment idempotency key was already used with different details."
        )
    if created:
        log_audit_event(
            actor=actor,
            verb="billing.payment_attempt_created",
            summary=(
                f"Payment attempt created for {locked_order.reference}: "
                f"{currency} {normalised_amount} via {provider}"
            ),
            target=attempt,
        )
    return attempt, created


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
    order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(
        pk=attempt.pk
    )
    locked_order = Order.objects.select_for_update().get(pk=order_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
    old_status = attempt.status
    if new_status == old_status:
        return attempt
    if new_status not in PAYMENT_TRANSITIONS.get(old_status, set()):
        raise ValidationError(
            f"Cannot move payment from {attempt.get_status_display()} to "
            f"{dict(PaymentAttempt.STATUS_CHOICES).get(new_status, new_status)}."
        )

    projected_paid_total = None
    if new_status == PaymentAttempt.STATUS_PAID:
        projected_paid_total = (
            _net_paid_total(
                locked_order,
                exclude_attempt_id=attempt.pk,
                lock_attempts=True,
            )
            + attempt.amount
        ).quantize(Decimal("0.01"))
        if projected_paid_total > locked_order.total:
            raise ValidationError(
                f"This payment would overpay order {locked_order.reference}. "
                f"Order total is {locked_order.total}; projected paid total is "
                f"{projected_paid_total}."
            )

    attempt.status = new_status
    external_reference = (external_reference or "").strip()[:160]
    if external_reference:
        duplicate_reference = PaymentAttempt.objects.exclude(pk=attempt.pk).filter(
            provider=attempt.provider,
            external_reference=external_reference,
        ).exists()
        if duplicate_reference:
            raise ValidationError(
                "This provider payment reference has already been recorded."
            )
        attempt.external_reference = external_reference
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
    try:
        with transaction.atomic():
            attempt.save(
                update_fields=[
                    "status",
                    "external_reference",
                    "last_error",
                    "completed_at",
                    "updated_at",
                ]
            )
    except IntegrityError as exc:
        raise ValidationError(
            "This provider payment reference has already been recorded."
        ) from exc

    if (
        new_status == PaymentAttempt.STATUS_PAID
        and projected_paid_total is not None
        and projected_paid_total >= locked_order.total
    ):
        commit_order_reservation(
            locked_order,
            actor=actor,
            reason=f"Payment {attempt.external_reference or attempt.pk} completed",
        )
        if auto_confirm_order and locked_order.status == Order.STATUS_PENDING:
            from commerce.fulfillment import transition_order

            transition_order(
                locked_order,
                Order.STATUS_CONFIRMED,
                actor=actor,
                note=f"Full payment confirmed via {attempt.provider}",
            )
    log_audit_event(
        actor=actor,
        verb="billing.payment_status_changed",
        summary=(
            f"{locked_order.reference}: payment {old_status} -> {new_status} "
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
    order_id = PaymentAttempt.objects.values_list("order_id", flat=True).get(
        pk=payment_attempt.pk
    )
    Order.objects.select_for_update().get(pk=order_id)
    payment_attempt = PaymentAttempt.objects.select_for_update().get(
        pk=payment_attempt.pk
    )
    if normalised_amount > payment_attempt.refundable_amount:
        existing = PaymentRefund.objects.filter(idempotency_key=key).first()
        if existing and (
            existing.payment_attempt_id == payment_attempt.pk
            and existing.amount == normalised_amount
        ):
            return existing, False
        raise ValidationError("Refund exceeds the remaining refundable amount.")
    refund, created = PaymentRefund.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "payment_attempt": payment_attempt,
            "amount": normalised_amount,
            "reason": (reason or "Refund")[:255],
            "external_reference": (external_reference or "")[:160],
            "processed_by": actor,
        },
    )
    if (
        refund.payment_attempt_id != payment_attempt.pk
        or refund.amount != normalised_amount
    ):
        raise ValidationError(
            "The refund idempotency key was already used with different details."
        )
    if not created:
        return refund, False
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
    event, created = PaymentWebhookEvent.objects.get_or_create(
        provider=provider,
        event_id=event_id,
        defaults={"payload_sha256": digest},
    )
    if event.payload_sha256 != digest:
        raise ValidationError(
            "A webhook event ID was reused with a different payload."
        )
    return event, created


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
