from django.contrib import admin

from marketing.models import (
    CampaignClick,
    CampaignLink,
    CaptionTemplate,
    MarketingCampaign,
    MarketingLead,
    ScheduledPost,
    SocialProfileSettings,
)


@admin.register(SocialProfileSettings)
class SocialProfileSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Social profiles",
            {
                "fields": (
                    "facebook_url",
                    "instagram_url",
                    "tiktok_url",
                    "x_url",
                    "linkedin_url",
                    "youtube_url",
                    "whatsapp_number",
                )
            },
        ),
        ("Sharing defaults", {"fields": ("default_share_message",)}),
    )

    def has_add_permission(self, request):
        return not SocialProfileSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "objective", "status", "start_date", "end_date", "budget")
    list_filter = ("objective", "status")
    search_fields = ("name", "target_audience", "notes")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CaptionTemplate)
class CaptionTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "is_active", "updated_at")
    list_filter = ("channel", "is_active")
    search_fields = ("name", "body", "hashtags")


@admin.register(CampaignLink)
class CampaignLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "campaign", "source", "medium", "click_count", "lead_count")
    list_filter = ("source", "medium", "campaign")
    search_fields = ("name", "code", "destination_url", "content")
    readonly_fields = ("code", "click_count", "lead_count", "last_clicked_at", "created_at")


@admin.register(CampaignClick)
class CampaignClickAdmin(admin.ModelAdmin):
    list_display = ("link", "occurred_at", "session_key")
    list_filter = ("occurred_at", "link__source")
    search_fields = ("link__name", "link__code", "session_key", "referrer")
    readonly_fields = ("link", "occurred_at", "session_key", "ip_hash", "user_agent", "referrer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ScheduledPost)
class ScheduledPostAdmin(admin.ModelAdmin):
    list_display = ("title", "campaign", "status", "scheduled_for", "published_at")
    list_filter = ("status", "scheduled_for", "campaign")
    search_fields = ("title", "caption", "notes")


@admin.register(MarketingLead)
class MarketingLeadAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "campaign", "status", "estimated_value", "created_at")
    list_filter = ("status", "source", "campaign")
    search_fields = ("name", "email", "phone", "notes")
    raw_id_fields = ("product", "assigned_to")
