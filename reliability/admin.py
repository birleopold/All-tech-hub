from django.contrib import admin

from reliability.models import (
    OrderReservation,
    PaymentAttempt,
    PaymentRefund,
    PaymentWebhookEvent,
)


class ReliabilityReadOnlyAdmin(admin.ModelAdmin):
    """Allow investigation without bypassing transaction service rules."""

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderReservation)
class OrderReservationAdmin(ReliabilityReadOnlyAdmin):
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
    date_hierarchy = "reserved_at"


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(ReliabilityReadOnlyAdmin):
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
    date_hierarchy = "created_at"


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ReliabilityReadOnlyAdmin):
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
    date_hierarchy = "processed_at"


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(ReliabilityReadOnlyAdmin):
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
    date_hierarchy = "received_at"
