from django.contrib import admin

from messaging.models import OutboundEmail


@admin.register(OutboundEmail)
class OutboundEmailAdmin(admin.ModelAdmin):
    list_display = ("to_email", "subject", "status", "created_at", "sent_at", "created_by")
    list_filter = ("status",)
    search_fields = ("to_email", "subject")
    raw_id_fields = ("created_by", "commercial_document", "job_card")
