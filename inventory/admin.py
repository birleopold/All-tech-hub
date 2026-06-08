from django.contrib import admin

from inventory.models import StockAdjustment, StockTake, StockTakeLine


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "quantity_delta", "reason", "job", "created_at", "created_by")
    list_filter = ("reason",)
    raw_id_fields = ("product", "job", "created_by")


class StockTakeLineInline(admin.TabularInline):
    model = StockTakeLine
    extra = 0
    raw_id_fields = ("product", "product_variant")
    fields = ("product", "product_variant", "system_quantity", "counted_quantity", "note")


@admin.register(StockTake)
class StockTakeAdmin(admin.ModelAdmin):
    list_display = ("reference", "name", "status", "created_by", "created_at", "posted_at")
    list_filter = ("status",)
    search_fields = ("reference", "name")
    inlines = [StockTakeLineInline]
    readonly_fields = ("reference", "posted_at")
