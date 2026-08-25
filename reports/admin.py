from django.contrib import admin

from reports.models import CustomerFollowUp


@admin.register(CustomerFollowUp)
class CustomerFollowUpAdmin(admin.ModelAdmin):
    list_display = (
        "customer", "follow_up_type", "status", "priority", "due_at", "assigned_to"
    )
    list_filter = ("follow_up_type", "status", "priority")
    search_fields = ("customer__name", "customer__email", "product_serial__serial_number")
    raw_id_fields = (
        "customer", "product_serial", "order", "assigned_to", "completed_by"
    )
    readonly_fields = ("created_at", "updated_at", "completed_at")
