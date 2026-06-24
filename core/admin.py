from django.contrib import admin

from core.models import (
    Announcement,
    AuditEvent,
    BusinessHours,
    CompanySettings,
    ContactMessage,
    KnowledgeArticle,
    LoginAttempt,
    StaffNotification,
    StaffNotificationPreference,
    StaffSavedSearch,
    StaffTwoFactor,
    SupportTicket,
    TicketComment,
)


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not CompanySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "created_at", "handled")
    list_filter = ("handled",)


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 0
    raw_id_fields = ("author",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("reference", "subject", "customer", "status", "priority", "assigned_to", "updated_at")
    list_filter = ("status", "priority")
    search_fields = ("reference", "subject", "customer__name", "customer__email")
    inlines = [TicketCommentInline]


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "is_internal", "created_at")
    list_filter = ("is_internal",)
    raw_id_fields = ("ticket", "author")


@admin.register(BusinessHours)
class BusinessHoursAdmin(admin.ModelAdmin):
    list_display = ("get_weekday_display", "is_open", "open_time", "close_time", "note")
    list_editable = ("is_open", "open_time", "close_time", "note")
    list_display_links = ("get_weekday_display",)


@admin.register(StaffNotificationPreference)
class StaffNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_on_assignment", "email_on_status_change", "inapp_enabled", "quiet_hours_start", "quiet_hours_end")
    raw_id_fields = ("user",)


@admin.register(StaffSavedSearch)
class StaffSavedSearchAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "user", "created_at")
    list_filter = ("scope",)


@admin.register(StaffNotification)
class StaffNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "message", "is_read", "created_at")
    list_filter = ("is_read",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "active_from", "active_until", "sort_order")
    list_filter = ("is_active",)


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "sort_order", "updated_at")
    list_filter = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "verb", "actor", "summary", "target_type", "target_id")
    list_filter = ("verb",)
    search_fields = ("summary", "target_type")
    readonly_fields = ("created_at", "actor", "verb", "summary", "target_type", "target_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.register(StaffTwoFactor)
admin.site.register(LoginAttempt)
