from django.contrib import admin

from operations.models import JobCard, JobFeedback, JobNote, JobStatusEvent, TimeEntry


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
