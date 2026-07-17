from django.contrib import admin

from loyalty.models import (
    CustomerMarketingPreference,
    LoyaltyAccount,
    LoyaltyTransaction,
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
        "unsubscribe_token",
        "consented_at",
        "withdrawn_at",
        "updated_at",
    )


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
