from django.contrib import admin

from automation.models import AutomationJob, PostAutomationPlan, PostChannelDelivery


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
