from django.contrib import admin

from billing.models import (
    CommercialDocument,
    CommercialLine,
    DocumentPayment,
    DocumentSequence,
)


class CommercialLineInline(admin.TabularInline):
    model = CommercialLine
    extra = 1
    raw_id_fields = ("product", "product_variant")


class DocumentPaymentInline(admin.TabularInline):
    model = DocumentPayment
    extra = 0
    raw_id_fields = ("recorded_by",)
    readonly_fields = ("recorded_at",)


@admin.register(CommercialDocument)
class CommercialDocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "doc_type", "customer", "status", "total", "issue_date")
    list_filter = ("doc_type", "status")
    search_fields = ("number", "customer__name", "customer__email")
    inlines = [CommercialLineInline, DocumentPaymentInline]
    raw_id_fields = ("customer", "order", "source_document", "created_by")


@admin.register(DocumentPayment)
class DocumentPaymentAdmin(admin.ModelAdmin):
    list_display = ("document", "amount", "method", "recorded_at", "recorded_by")
    list_filter = ("method",)
    raw_id_fields = ("document", "recorded_by")


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("key", "year", "last_value")
