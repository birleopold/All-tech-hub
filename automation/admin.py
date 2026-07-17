from django.contrib import admin

from automation.models import (
    AutomationControl,
    AutomationJob,
    AutomationJobEvent,
    AutomationRun,
    PostAutomationPlan,
    PostChannelDelivery,
)


class ReadOnlyAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostAutomationPlan)
class PostAutomationPlanAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("post", "mode", "status", "updated_at")
    list_filter = ("mode", "status")
    search_fields = ("post__title", "post__caption", "last_error")
    date_hierarchy = "updated_at"


@admin.register(PostChannelDelivery)
class PostChannelDeliveryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "post",
        "channel",
        "method",
        "status",
        "attempt_count",
        "published_at",
    )
    list_filter = ("channel", "method", "status")
    search_fields = ("post__title", "external_id", "external_url", "last_error")
    date_hierarchy = "created_at"


@admin.register(AutomationJob)
class AutomationJobAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "idempotency_key",
        "job_type",
        "status",
        "attempt_count",
        "next_attempt_at",
        "completed_at",
    )
    list_filter = ("job_type", "status")
    search_fields = ("idempotency_key", "locked_by", "last_error")
    date_hierarchy = "created_at"


@admin.register(AutomationControl)
class AutomationControlAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "singleton_key",
        "is_paused",
        "last_run_status",
        "last_heartbeat_at",
        "consecutive_failures",
        "updated_at",
    )
    readonly_fields = (
        "singleton_key",
        "is_paused",
        "paused_job_types",
        "pause_reason",
        "paused_by",
        "paused_at",
        "resumed_by",
        "resumed_at",
        "last_heartbeat_at",
        "last_run_started_at",
        "last_run_finished_at",
        "last_run_status",
        "last_worker_id",
        "last_summary",
        "consecutive_failures",
        "updated_at",
    )


@admin.register(AutomationRun)
class AutomationRunAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "source", "status", "worker_id", "started_at", "finished_at")
    list_filter = ("source", "status")
    search_fields = ("worker_id", "error")
    date_hierarchy = "started_at"


@admin.register(AutomationJobEvent)
class AutomationJobEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("job", "action", "actor", "occurred_at")
    list_filter = ("action", "job__job_type")
    search_fields = ("job__idempotency_key", "message", "actor__username")
    date_hierarchy = "occurred_at"
