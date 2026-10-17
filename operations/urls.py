from django.urls import path

from core import private_views
from operations import views
from operations.job_list_view import StaffJobCardListView

urlpatterns = [
    path("jobs/bench/", views.TechnicianBenchView.as_view(), name="staff_job_bench"),
    path("jobs/", StaffJobCardListView.as_view(), name="staff_jobs"),
    path("jobs/calendar/", views.JobScheduleCalendarView.as_view(), name="staff_job_calendar"),
    path("jobs/<int:pk>/reschedule/", views.staff_job_reschedule, name="staff_job_reschedule"),
    path("jobs/new/", views.JobCardCreateView.as_view(), name="staff_job_create"),
    path("jobs/<int:pk>/", views.JobCardDetailView.as_view(), name="staff_job_detail"),
    path("jobs/<int:pk>/bench/", views.JobBenchDetailView.as_view(), name="staff_job_bench_detail"),
    path("jobs/<int:pk>/bench/status/", views.job_bench_status, name="staff_job_bench_status"),
    path("jobs/<int:pk>/edit/", views.JobCardUpdateView.as_view(), name="staff_job_edit"),
    path("jobs/<int:pk>/note/", views.job_add_note, name="staff_job_note"),
    path("jobs/<int:pk>/expense/", views.job_add_expense, name="staff_job_expense"),
    path("jobs/<int:pk>/pdf/", views.job_pdf_view, name="staff_job_pdf"),
    path("jobs/<int:pk>/labels/", views.job_label_sheet, name="staff_job_labels"),
    path("jobs/<int:pk>/time/", views.job_add_time, name="staff_job_time"),
    path("jobs/<int:pk>/attachment/", views.job_add_attachment, name="staff_job_attachment"),
    path(
        "jobs/attachments/<int:pk>/file/",
        private_views.staff_job_attachment,
        name="staff_job_attachment_file",
    ),
    path(
        "jobs/<int:pk>/signature/",
        private_views.staff_job_signature,
        name="staff_job_signature",
    ),
]
