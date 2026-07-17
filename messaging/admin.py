from django.contrib import admin

from messaging.models import EmailDeliveryEvent, EmailSuppression, OutboundEmail


class ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboundEmail)
class OutboundEmailAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "to_email",
        "category",
        "subject",
        "status",
        "attempt_count",
        "created_at",
        "accepted_at",
        "delivered_at",
    )
    list_filter = ("category", "status", "provider")
    search_fields = (
        "to_email",
        "normalized_to_email",
        "subject",
        "provider_message_id",
        "idempotency_key",
    )
    raw_id_fields = ("created_by", "commercial_document", "job_card")
    date_hierarchy = "created_at"


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "email_address",
        "scope",
        "reason",
        "source",
        "is_active",
        "event_count",
        "last_seen_at",
    )
    list_filter = ("is_active", "scope", "reason", "source")
    search_fields = ("email_address", "release_reason")
    date_hierarchy = "last_seen_at"


@admin.register(EmailDeliveryEvent)
class EmailDeliveryEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "event_key",
        "email_address",
        "event_type",
        "provider",
        "occurred_at",
        "outbound_email",
    )
    list_filter = ("event_type", "provider")
    search_fields = (
        "event_key",
        "email_address",
        "provider_message_id",
        "payload_hash",
    )
    raw_id_fields = ("outbound_email",)
    date_hierarchy = "occurred_at"
