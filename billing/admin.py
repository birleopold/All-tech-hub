from django.contrib import admin

from billing.models import (
    AccountPayment,
    CommercialDocument,
    CommercialLine,
    CustomerCredit,
    DocumentPayment,
    DocumentRevision,
    DocumentSequence,
    DocumentTemplate,
    PaymentAllocation,
    PaymentRefund,
)


class CommercialLineInline(admin.TabularInline):
    model = CommercialLine
    extra = 1
    raw_id_fields = ("product", "product_variant")
    fields = (
        "sort_order",
        "source_type",
        "product",
        "product_variant",
        "description",
        "quantity",
        "unit_price",
        "unit_cost",
        "discount_type",
        "discount_value",
        "tax_rate",
    )


class DocumentPaymentInline(admin.TabularInline):
    model = DocumentPayment
    extra = 0
    raw_id_fields = ("recorded_by",)
    readonly_fields = ("recorded_at",)


@admin.register(CommercialDocument)
class CommercialDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "doc_type",
        "document_customer",
        "status",
        "total",
        "issue_date",
    )
    list_filter = ("doc_type", "status")
    search_fields = (
        "number",
        "customer_name",
        "customer_email",
        "customer__name",
        "customer__email",
    )
    inlines = [CommercialLineInline, DocumentPaymentInline]
    raw_id_fields = ("customer", "order", "source_document", "created_by")

    @admin.display(description="Customer")
    def document_customer(self, obj):
        return obj.display_customer_name


@admin.register(DocumentPayment)
class DocumentPaymentAdmin(admin.ModelAdmin):
    list_display = ("document", "amount", "method", "recorded_at", "recorded_by")
    list_filter = ("method",)
    raw_id_fields = ("document", "recorded_by")


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("key", "year", "last_value")


admin.site.register(PaymentRefund)
admin.site.register(DocumentRevision)
admin.site.register(DocumentTemplate)
admin.site.register(CustomerCredit)
admin.site.register(AccountPayment)
admin.site.register(PaymentAllocation)
