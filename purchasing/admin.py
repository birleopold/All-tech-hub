from django.contrib import admin

from purchasing.models import (
    PurchaseLine,
    PurchaseOrder,
    StockReceipt,
    StockReceiptLine,
    Supplier,
    SupplierReturn,
)


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 1
    raw_id_fields = ("product",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "created_at")
    search_fields = ("name", "email", "phone")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "status", "ordered_on", "expected_on")
    list_filter = ("status", "supplier")
    search_fields = ("number", "supplier__name")
    raw_id_fields = ("supplier", "created_by")
    inlines = [PurchaseLineInline]


class StockReceiptLineInline(admin.TabularInline):
    model = StockReceiptLine
    extra = 1
    raw_id_fields = ("purchase_line",)


@admin.register(StockReceipt)
class StockReceiptAdmin(admin.ModelAdmin):
    list_display = ("number", "purchase_order", "received_on", "received_by")
    raw_id_fields = ("purchase_order", "received_by")
    inlines = [StockReceiptLineInline]


@admin.register(StockReceiptLine)
class StockReceiptLineAdmin(admin.ModelAdmin):
    list_display = ("receipt", "purchase_line", "quantity_received")
    raw_id_fields = ("receipt", "purchase_line")


admin.site.register(SupplierReturn)
