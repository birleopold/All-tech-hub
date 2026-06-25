from django.urls import path

from operations import views

urlpatterns = [
    path("jobs/bench/", views.TechnicianBenchView.as_view(), name="staff_job_bench"),
    path("jobs/", views.JobCardListView.as_view(), name="staff_jobs"),
    path("jobs/calendar/", views.JobScheduleCalendarView.as_view(), name="staff_job_calendar"),
    path("jobs/<int:pk>/reschedule/", views.staff_job_reschedule, name="staff_job_reschedule"),
    path("jobs/new/", views.JobCardCreateView.as_view(), name="staff_job_create"),
    path("jobs/<int:pk>/", views.JobCardDetailView.as_view(), name="staff_job_detail"),
    path("jobs/<int:pk>/bench/", views.JobBenchDetailView.as_view(), name="staff_job_bench_detail"),
    path("jobs/<int:pk>/bench/status/", views.job_bench_status, name="staff_job_bench_status"),
    path("jobs/<int:pk>/edit/", views.JobCardUpdateView.as_view(), name="staff_job_edit"),
    path("jobs/<int:pk>/note/", views.job_add_note, name="staff_job_note"),
    path("jobs/<int:pk>/pdf/", views.job_pdf_view, name="staff_job_pdf"),
    path("jobs/<int:pk>/labels/", views.job_label_sheet, name="staff_job_labels"),
    path("jobs/<int:pk>/time/", views.job_add_time, name="staff_job_time"),
    path("jobs/<int:pk>/attachment/", views.job_add_attachment, name="staff_job_attachment"),
]
