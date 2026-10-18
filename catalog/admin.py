from django.contrib import admin

from catalog.models import (
    Category,
    Product,
    ProductImage,
    ProductReview,
    ProductSerial,
    ProductVariant,
    WishlistItem,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "slug")
    list_filter = ("parent",)
    search_fields = ("name", "description", "slug", "seo_title", "seo_description")
    fieldsets = (
        ("Category", {"fields": ("name", "slug", "parent", "description", "sort_order")}),
        ("Google Search — optional overrides", {
            "fields": ("seo_title", "seo_description", "seo_heading"),
            "description": "Edit the short search preview independently of the public catalogue layout. Don't add unverified claims.",
        }),
    )
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kind",
        "category",
        "price",
        "stock_quantity",
        "reorder_level",
        "is_published",
        "is_featured",
    )
    list_filter = ("kind", "category", "is_published", "is_featured")
    search_fields = ("name", "sku", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariantInline]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "rating", "display_name", "is_published", "is_verified_purchase", "created_at")
    list_filter = ("is_published", "is_verified_purchase", "rating")
    search_fields = ("product__name", "author_name", "body")
    raw_id_fields = ("product", "customer", "moderated_by")
    actions = ("approve_reviews",)

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        from django.utils import timezone

        queryset.update(is_published=True, moderated_at=timezone.now(), moderated_by=request.user)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("customer", "product", "created_at")
    raw_id_fields = ("customer", "product")
    search_fields = ("customer__name", "product__name")


@admin.register(ProductSerial)
class ProductSerialAdmin(admin.ModelAdmin):
    list_display = (
        "serial_number",
        "product",
        "product_variant",
        "status",
        "sold_to",
        "sold_at",
        "warranty_months",
    )
    list_filter = ("status",)
    search_fields = ("serial_number", "imei", "mac_address", "product__name", "sold_to__name")
    raw_id_fields = ("product", "product_variant", "sold_to")
