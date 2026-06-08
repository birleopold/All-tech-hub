from django.contrib import admin

from commerce.models import Coupon, Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    raw_id_fields = ("product", "product_variant")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "status", "total", "discount_amount", "coupon_code_applied", "placed_at")
    list_filter = ("status",)
    search_fields = ("reference", "contact_email", "contact_name", "coupon_code_applied")
    inlines = [OrderLineInline]
    raw_id_fields = ("customer", "user")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "min_subtotal", "times_used", "max_uses", "is_active", "active_until")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "description")
