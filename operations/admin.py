from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from operations.models import JobCard, JobExpense, JobFeedback, JobHandover, JobNote, JobStatusEvent, TimeEntry


class JobNoteInline(admin.TabularInline):
    model = JobNote
    extra = 0
    raw_id_fields = ("author",)


@admin.register(JobCard)
class JobCardAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "customer", "status", "priority", "received_on")
    list_filter = ("status", "priority")
    search_fields = ("number", "title", "serial_number", "customer__name")
    inlines = [JobNoteInline]
    raw_id_fields = ("customer", "assigned_to", "related_order", "related_invoice")


@admin.register(JobNote)
class JobNoteAdmin(admin.ModelAdmin):
    list_display = ("job", "author", "created_at", "is_internal")
    raw_id_fields = ("job", "author")


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("job", "technician", "started_at", "ended_at", "minutes", "is_billable")
    list_filter = ("is_billable", "technician")
    raw_id_fields = ("job", "technician")


@admin.register(JobStatusEvent)
class JobStatusEventAdmin(admin.ModelAdmin):
    list_display = ("job", "from_status", "to_status", "actor", "created_at")
    list_filter = ("to_status",)
    raw_id_fields = ("job", "actor")


@admin.register(JobFeedback)
class JobFeedbackAdmin(admin.ModelAdmin):
    list_display = ("job", "rating", "submitted_at")
    list_filter = ("rating",)
    raw_id_fields = ("job",)


@admin.register(JobExpense)
class JobExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "job", "category", "description", "reference",
        "amount", "recorded_by", "recorded_at",
    )
    list_filter = ("category", "recorded_at")
    search_fields = ("job__number", "reference", "description")
    raw_id_fields = ("job", "recorded_by")
    readonly_fields = (
        "job", "category", "description", "reference",
        "amount", "recorded_by", "recorded_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JobHandover)
class JobHandoverAdmin(admin.ModelAdmin):
    list_display = ("job", "method", "recipient_name", "recorded_by", "recorded_at")
    list_filter = ("method", "recorded_at")
    search_fields = ("job__number", "recipient_name")
    raw_id_fields = ("job", "recorded_by")
    readonly_fields = (
        "job", "method", "recipient_name", "note", "protected_signature",
        "recorded_by", "recorded_at",
    )

    @admin.display(description="Recipient signature")
    def protected_signature(self, obj):
        if not obj or not obj.pk or not obj.signature:
            return "Not captured (legacy handover)"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">View protected signature</a>',
            reverse("staff_job_handover_signature", args=[obj.job_id]),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
