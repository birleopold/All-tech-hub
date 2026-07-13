from django.contrib import admin

from marketing.models import SocialProfileSettings


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
