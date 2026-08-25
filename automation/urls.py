from django.urls import path

from automation import staff_views


urlpatterns = [
    path(
        "automation/",
        staff_views.AutomationControlDashboardView.as_view(),
        name="staff_automation_control",
    ),
    path(
        "automation/pause/",
        staff_views.automation_pause,
        name="staff_automation_pause",
    ),
    path(
        "automation/resume/",
        staff_views.automation_resume,
        name="staff_automation_resume",
    ),
    path(
        "automation/jobs/<int:pk>/",
        staff_views.automation_job_detail,
        name="staff_automation_job_detail",
    ),
    path(
        "automation/jobs/<int:pk>/replay/",
        staff_views.automation_job_replay,
        name="staff_automation_job_replay",
    ),
    path(
        "automation/jobs/<int:pk>/cancel/",
        staff_views.automation_job_cancel,
        name="staff_automation_job_cancel",
    ),
]
