from django.contrib import admin

from growth.models import (
    Ambassador,
    AmbassadorClick,
    AmbassadorConversion,
    AmbassadorLead,
    ContentAsset,
    DistributionGroup,
    GrowthSettings,
    ProductGrowthData,
    SavedCart,
    StockAlertSubscription,
)


@admin.register(GrowthSettings)
class GrowthSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Analytics and verification",
            {
                "fields": (
                    "ga4_measurement_id",
                    "search_console_verification_token",
                    "clarity_project_id",
                    "require_analytics_consent",
                    "privacy_policy_url",
                )
            },
        ),
        (
            "Google Business Profile",
            {
                "fields": (
                    "google_business_profile_url",
                    "google_review_url",
                    "google_place_id",
                )
            },
        ),
        (
            "Merchant Center",
            {
                "fields": (
                    "merchant_country",
                    "merchant_language",
                    "merchant_default_brand",
                    "merchant_shipping_service",
                    "merchant_shipping_price",
                    "merchant_return_policy_url",
                )
            },
        ),
        (
            "Automation",
            {
                "fields": (
                    "abandoned_cart_enabled",
                    "abandoned_cart_first_delay_hours",
                    "abandoned_cart_second_delay_hours",
                    "back_in_stock_enabled",
                    "default_content_hashtags",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return not GrowthSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductGrowthData)
class ProductGrowthDataAdmin(admin.ModelAdmin):
    list_display = ("product", "brand", "condition", "gtin", "mpn", "updated_at")
    list_filter = ("condition", "brand")
    search_fields = ("product__name", "product__sku", "brand", "gtin", "mpn")
    raw_id_fields = ("product",)


@admin.register(StockAlertSubscription)
class StockAlertSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "product", "alert_type", "target_price", "is_active", "notified_at")
    list_filter = ("alert_type", "is_active", "notified_at")
    search_fields = ("email", "phone", "product__name")
    raw_id_fields = ("product",)


@admin.register(SavedCart)
class SavedCartAdmin(admin.ModelAdmin):
    list_display = ("email", "subtotal", "status", "last_activity", "first_reminder_sent_at", "second_reminder_sent_at")
    list_filter = ("status", "last_activity")
    search_fields = ("email", "phone", "customer_name", "session_key")
    readonly_fields = ("recovery_token", "consent_at", "created_at", "updated_at")


@admin.register(ContentAsset)
class ContentAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "asset_type", "product", "campaign", "status", "created_at")
    list_filter = ("asset_type", "status", "campaign")
    search_fields = ("title", "body", "product__name")
    raw_id_fields = ("product", "campaign", "created_by")


@admin.register(DistributionGroup)
class DistributionGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "audience", "is_active", "last_posted_at", "tracking_link")
    list_filter = ("platform", "is_active")
    search_fields = ("name", "audience", "rules", "notes")
    raw_id_fields = ("tracking_link", "created_by")


@admin.register(Ambassador)
class AmbassadorAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "click_count", "lead_count", "order_count", "revenue_total")
    list_filter = ("is_active", "commission_type")
    search_fields = ("name", "code", "email", "phone")
    readonly_fields = ("click_count", "lead_count", "order_count", "revenue_total", "created_at", "updated_at")


@admin.register(AmbassadorConversion)
class AmbassadorConversionAdmin(admin.ModelAdmin):
    list_display = ("ambassador", "order", "revenue", "commission_amount", "status", "created_at")
    list_filter = ("status", "ambassador")
    search_fields = ("ambassador__name", "ambassador__code", "order__reference")
    raw_id_fields = ("ambassador", "order")


@admin.register(AmbassadorClick)
class AmbassadorClickAdmin(admin.ModelAdmin):
    list_display = ("ambassador", "occurred_at", "session_key")
    list_filter = ("ambassador", "occurred_at")
    readonly_fields = ("ambassador", "occurred_at", "session_key", "ip_hash", "user_agent", "referrer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AmbassadorLead)
class AmbassadorLeadAdmin(admin.ModelAdmin):
    list_display = ("ambassador", "lead", "created_at")
    raw_id_fields = ("ambassador", "lead")
