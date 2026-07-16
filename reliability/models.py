from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from commerce.models import Order


class OrderReservation(models.Model):
    STATUS_RESERVED = "reserved"
    STATUS_COMMITTED = "committed"
    STATUS_RELEASED = "released"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_RESERVED, "Reserved"),
        (STATUS_COMMITTED, "Committed"),
        (STATUS_RELEASED, "Released"),
        (STATUS_EXPIRED, "Expired"),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="stock_reservation",
    )
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RESERVED,
        db_index=True,
    )
    expires_at = models.DateTimeField(db_index=True)
    reserved_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_reservations_created",
    )

    class Meta:
        ordering = ["expires_at", "id"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="reservation_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.order.reference} — {self.get_status_display()}"

    @property
    def is_active(self) -> bool:
        return self.status in {self.STATUS_RESERVED, self.STATUS_COMMITTED}

    @property
    def is_expired(self) -> bool:
        return self.status == self.STATUS_RESERVED and self.expires_at <= timezone.now()


class PaymentAttempt(models.Model):
    STATUS_CREATED = "created"
    STATUS_PENDING = "pending"
    STATUS_AUTHORISED = "authorised"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"
    STATUS_PARTIALLY_REFUNDED = "partial_refund"
    STATUS_REFUNDED = "refunded"
    STATUS_DISPUTED = "disputed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PENDING, "Pending"),
        (STATUS_AUTHORISED, "Authorised"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_PARTIALLY_REFUNDED, "Partially refunded"),
        (STATUS_REFUNDED, "Refunded"),
        (STATUS_DISPUTED, "Disputed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    provider = models.CharField(max_length=64, default="manual", db_index=True)
    external_reference = models.CharField(max_length=160, blank=True, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="UGX")
    safe_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-secret provider metadata only. Never store credentials or raw payment secrets.",
    )
    request_fingerprint = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["order", "status"], name="payment_order_status_idx"),
            models.Index(fields=["provider", "external_reference"], name="payment_provider_ref_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_attempt_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["provider", "external_reference"],
                condition=~models.Q(external_reference=""),
                name="unique_provider_payment_reference",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order.reference} — {self.provider} — {self.get_status_display()}"

    @property
    def is_successful(self) -> bool:
        return self.status in {
            self.STATUS_PAID,
            self.STATUS_PARTIALLY_REFUNDED,
            self.STATUS_REFUNDED,
        }

    @property
    def refundable_amount(self) -> Decimal:
        if self.status not in {
            self.STATUS_PAID,
            self.STATUS_PARTIALLY_REFUNDED,
            self.STATUS_DISPUTED,
        }:
            return Decimal("0")
        refunded = sum(
            self.refunds.values_list("amount", flat=True),
            Decimal("0"),
        )
        return max(Decimal("0"), self.amount - refunded).quantize(Decimal("0.01"))


class PaymentRefund(models.Model):
    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    external_reference = models.CharField(max_length=160, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_attempt_refunds_processed",
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-processed_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_refund_amount_positive",
            )
        ]

    def __str__(self) -> str:
        return f"Refund {self.amount} for {self.payment_attempt.order.reference}"


class PaymentWebhookEvent(models.Model):
    STATUS_RECEIVED = "received"
    STATUS_PROCESSED = "processed"
    STATUS_IGNORED = "ignored"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RECEIVED, "Received"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_IGNORED, "Ignored"),
        (STATUS_FAILED, "Failed"),
    ]

    provider = models.CharField(max_length=64)
    event_id = models.CharField(max_length=180)
    payload_sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
        db_index=True,
    )
    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
    )
    last_error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="unique_provider_webhook_event",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"
