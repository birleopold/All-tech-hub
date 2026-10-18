from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from merchandising.models import (
    BuyingGuide,
    HomepagePromotion,
    CommercialLandingFAQ,
    CommercialLandingPage,
    DeliveryZone,
    ProductCommerceProfile,
    SearchQueryInsight,
)


class CommercialLandingFAQInline(admin.TabularInline):
    model = CommercialLandingFAQ
    extra = 1


@admin.register(CommercialLandingPage)
class CommercialLandingPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "brand", "condition", "is_published", "sort_order", "updated_at")
    list_filter = ("is_published", "condition", "brand")
    search_fields = ("title", "slug", "intro", "search_terms", "category_keywords")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [CommercialLandingFAQInline]
    fieldsets = (
        ("Page identity", {"fields": ("title", "slug", "eyebrow", "meta_description", "is_published", "sort_order")}),
        ("People-first content", {"fields": ("intro", "buying_guidance")}),
        ("Live catalogue selection", {"fields": ("category_keywords", "brand", "condition", "search_terms")}),
        ("Conversion", {"fields": ("hero_cta", "hero_cta_url")}),
    )


@admin.register(BuyingGuide)
class BuyingGuideAdmin(admin.ModelAdmin):
    list_display = ("title", "author_name", "reviewer_name", "is_published", "published_at", "updated_at")
    list_filter = ("is_published", "published_at")
    search_fields = ("title", "excerpt", "body", "keywords")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"


@admin.action(description="Mark identity, condition, price and stock verified now")
def mark_verified_now(modeladmin, request, queryset):
    now = timezone.now()
    queryset.update(
        identity_verified_at=now,
        condition_verified_at=now,
        stock_confirmed_at=now,
        price_verified_at=now,
    )


@admin.action(description="Disable Merchant publication for selected records")
def disable_merchant(modeladmin, request, queryset):
    queryset.update(merchant_enabled=False)


@admin.register(ProductCommerceProfile)
class ProductCommerceProfileAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "condition_label",
        "merchant_enabled",
        "readiness_badge",
        "actual_photos",
        "warranty_months",
        "condition_verified_at",
        "stock_confirmed_at",
    )
    list_filter = (
        "merchant_enabled",
        "actual_photos",
        "merchant_free_shipping",
        "charger_included",
        "condition_verified_at",
    )
    search_fields = (
        "product__name",
        "product__sku",
        "processor_family",
        "ram_capacity",
        "storage_capacity",
        "graphics",
    )
    autocomplete_fields = ("product",)
    actions = (mark_verified_now, disable_merchant)
    readonly_fields = ("readiness_report", "updated_at")
    fieldsets = (
        ("Product", {"fields": ("product", "actual_photos", "condition_notes")}),
        ("Core specifications", {"fields": (
            ("processor_family", "processor_generation"),
            ("ram_capacity", "ram_type"),
            ("storage_capacity", "storage_type"),
            ("screen_size", "screen_resolution", "touchscreen"),
            "graphics",
            "operating_system",
        )}),
        ("Physical inspection", {"fields": (
            "battery_health_note",
            "keyboard_condition",
            "charger_included",
            "accessories_included",
            "warranty_months",
            ("identity_verified_at", "condition_verified_at"),
        )}),
        ("Availability and delivery", {"fields": (
            "delivery_note",
            "stock_confirmed_at",
            "price_verified_at",
        )}),
        ("Merchant Center", {"fields": (
            "merchant_enabled",
            "merchant_shipping_price",
            "merchant_free_shipping",
            "readiness_report",
        )}),
        ("Audit", {"fields": ("updated_at",)}),
    )

    @admin.display(description="Condition")
    def condition_label(self, obj):
        try:
            return obj.product.growth_data.get_condition_display()
        except Exception:
            return "Missing"

    @admin.display(description="Readiness")
    def readiness_badge(self, obj):
        score = obj.merchant_readiness_score
        label = "Ready" if obj.is_merchant_ready else f"{score}%"
        color = "#198754" if obj.is_merchant_ready else "#b45309"
        return format_html('<strong style="color:{}">{}</strong>', color, label)

    @admin.display(description="Merchant readiness details")
    def readiness_report(self, obj):
        if not obj or not obj.pk:
            return "Save the profile to calculate readiness."
        missing = obj.merchant_missing_fields()
        if not missing:
            return "Ready for strict Merchant publication."
        return format_html(
            "<strong>{}% ready</strong><br>{}",
            obj.merchant_readiness_score,
            format_html_join("", "• {}<br>", ((item,) for item in missing)),
        )


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "areas", "fee_from", "lead_time", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "areas", "notes")


@admin.register(SearchQueryInsight)
class SearchQueryInsightAdmin(admin.ModelAdmin):
    list_display = ("query", "page", "clicks", "impressions", "ctr", "position", "date_end", "imported_at")
    list_filter = ("date_end", "imported_at")
    search_fields = ("query", "page")
    readonly_fields = ("imported_at",)


@admin.register(HomepagePromotion)
class HomepagePromotionAdmin(admin.ModelAdmin):
    list_display = ("headline", "slot", "is_active", "priority", "start_at", "end_at", "updated_at")
    list_filter = ("slot", "is_active")
    search_fields = ("headline", "eyebrow", "supporting_text")
    autocomplete_fields = ("product",)
    list_editable = ("is_active", "priority")
    fieldsets = (
        ("Placement", {"fields": ("slot", "priority", "is_active", "start_at", "end_at")}),
        ("Campaign message", {"fields": ("eyebrow", "headline", "supporting_text", "button_label", "link_path")}),
        ("Visual", {"fields": ("product", "creative_image", "image_alt")}),
    )
