from django.contrib import admin

from reliability.models import (
    OrderReservation,
    PaymentAttempt,
    PaymentRefund,
    PaymentWebhookEvent,
)


@admin.register(OrderReservation)
class OrderReservationAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "status",
        "expires_at",
        "reserved_at",
        "committed_at",
        "released_at",
    )
    list_filter = ("status",)
    search_fields = ("order__reference", "idempotency_key", "release_reason")
    readonly_fields = (
        "idempotency_key",
        "reserved_at",
        "committed_at",
        "released_at",
    )
    date_hierarchy = "reserved_at"


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "provider",
        "status",
        "amount",
        "currency",
        "external_reference",
        "created_at",
    )
    list_filter = ("provider", "status", "currency")
    search_fields = (
        "order__reference",
        "idempotency_key",
        "external_reference",
    )
    readonly_fields = (
        "idempotency_key",
        "request_fingerprint",
        "created_at",
        "updated_at",
        "completed_at",
    )
    date_hierarchy = "created_at"


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = (
        "payment_attempt",
        "amount",
        "external_reference",
        "processed_by",
        "processed_at",
    )
    search_fields = (
        "payment_attempt__order__reference",
        "idempotency_key",
        "external_reference",
        "reason",
    )
    readonly_fields = ("idempotency_key", "processed_at")
    date_hierarchy = "processed_at"


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "event_id",
        "status",
        "payment_attempt",
        "received_at",
        "processed_at",
    )
    list_filter = ("provider", "status")
    search_fields = ("event_id", "payload_sha256", "payment_attempt__order__reference")
    readonly_fields = (
        "provider",
        "event_id",
        "payload_sha256",
        "received_at",
        "processed_at",
    )
    date_hierarchy = "received_at"
