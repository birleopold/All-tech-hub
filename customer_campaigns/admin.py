from django.contrib import admin

from customer_campaigns.models import (
    CampaignAutomationEvent,
    CustomerCampaign,
    CustomerCampaignRecipient,
)


@admin.register(CustomerCampaign)
class CustomerCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "topic",
        "segment",
        "status",
        "next_run_at",
        "prepared_count",
        "sent_count",
        "suppressed_count",
        "failed_count",
        "updated_at",
    )
    list_filter = (
        "status",
        "automated_delivery",
        "topic",
        "segment",
        "channel",
    )
    search_fields = ("name", "subject")
    readonly_fields = (
        "name",
        "marketing_campaign",
        "channel",
        "topic",
        "segment",
        "subject",
        "body",
        "max_recipients",
        "status",
        "prepared_count",
        "sent_count",
        "suppressed_count",
        "failed_count",
        "approval_note",
        "failure_reason",
        "automated_delivery",
        "scheduled_for",
        "next_run_at",
        "automation_batch_size",
        "approval_expires_at",
        "scheduled_at",
        "paused_at",
        "pause_reason",
        "last_automation_at",
        "automation_run_count",
        "created_by",
        "prepared_by",
        "approved_by",
        "scheduled_by",
        "paused_by",
        "sent_by",
        "prepared_at",
        "approved_at",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerCampaignRecipient)
class CustomerCampaignRecipientAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "customer",
        "email_address",
        "status",
        "consent_event",
        "outbound_email",
        "attempted_at",
        "sent_at",
    )
    list_filter = ("status", "campaign__topic", "campaign__segment")
    search_fields = (
        "campaign__name",
        "customer__name",
        "customer__email",
        "email_address",
    )
    readonly_fields = (
        "campaign",
        "customer",
        "email_address",
        "status",
        "suppression_reason",
        "consent_event",
        "outbound_email",
        "prepared_at",
        "attempted_at",
        "sent_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignAutomationEvent)
class CampaignAutomationEventAdmin(admin.ModelAdmin):
    list_display = ("campaign", "action", "actor", "message", "occurred_at")
    list_filter = ("action",)
    search_fields = ("campaign__name", "message", "actor__username")
    readonly_fields = (
        "campaign",
        "action",
        "actor",
        "message",
        "metadata",
        "occurred_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
