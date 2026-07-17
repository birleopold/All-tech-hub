from django.contrib import admin

from loyalty.models import (
    CustomerMarketingPreference,
    LoyaltyAccount,
    LoyaltyTransaction,
    MarketingConsentEvent,
)


@admin.register(CustomerMarketingPreference)
class CustomerMarketingPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "email_marketing",
        "whatsapp_marketing",
        "product_updates",
        "special_offers",
        "consent_source",
        "consented_at",
        "withdrawn_at",
    )
    list_filter = (
        "email_marketing",
        "whatsapp_marketing",
        "product_updates",
        "special_offers",
        "consent_source",
    )
    search_fields = ("customer__name", "customer__email", "customer__phone")
    readonly_fields = (
        "customer",
        "email_marketing",
        "whatsapp_marketing",
        "product_updates",
        "special_offers",
        "consent_source",
        "consent_text_version",
        "unsubscribe_token",
        "consented_at",
        "withdrawn_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MarketingConsentEvent)
class MarketingConsentEventAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "action",
        "source",
        "email_marketing",
        "whatsapp_marketing",
        "product_updates",
        "special_offers",
        "created_at",
    )
    list_filter = ("action", "source", "email_marketing", "whatsapp_marketing")
    search_fields = ("customer__name", "customer__email", "customer__phone")
    readonly_fields = (
        "preference",
        "customer",
        "action",
        "source",
        "email_marketing",
        "whatsapp_marketing",
        "product_updates",
        "special_offers",
        "consent_text_version",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyAccount)
class LoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = ("customer", "tier", "points_balance", "lifetime_points", "updated_at")
    list_filter = ("tier",)
    search_fields = ("customer__name", "customer__email", "customer__phone")
    readonly_fields = (
        "customer",
        "points_balance",
        "lifetime_points",
        "tier",
        "joined_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ("account", "kind", "points_delta", "order_reference", "created_at")
    list_filter = ("kind",)
    search_fields = (
        "account__customer__name",
        "account__customer__email",
        "order_reference",
        "idempotency_key",
    )
    readonly_fields = (
        "account",
        "kind",
        "points_delta",
        "idempotency_key",
        "order_reference",
        "note",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
