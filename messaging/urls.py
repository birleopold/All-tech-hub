from django.urls import path

from messaging import deliverability_views, views, workspace_views

urlpatterns = [
    path("email/document/<int:pk>/", views.email_document, name="staff_email_document"),
    path("email/job/<int:pk>/", views.email_jobcard, name="staff_email_jobcard"),
    path(
        "email/job/<int:pk>/update/",
        views.email_job_update,
        name="staff_email_job_update",
    ),
    path("email/log/", workspace_views.EmailWorkspaceListView.as_view(), name="staff_email_log"),
    path(
        "email/log/<int:pk>/",
        views.email_log_detail,
        name="staff_email_log_detail",
    ),
    path(
        "email/log/<int:pk>/retry/",
        views.email_log_retry,
        name="staff_email_log_retry",
    ),
    path(
        "email/deliverability/",
        deliverability_views.EmailDeliverabilityDashboardView.as_view(),
        name="staff_email_deliverability",
    ),
    path(
        "email/deliverability/suppress/",
        deliverability_views.email_suppression_add,
        name="staff_email_suppression_add",
    ),
    path(
        "email/deliverability/suppressions/<int:pk>/",
        deliverability_views.email_suppression_detail,
        name="staff_email_suppression_detail",
    ),
    path(
        "email/deliverability/suppressions/<int:pk>/release/",
        deliverability_views.email_suppression_release,
        name="staff_email_suppression_release",
    ),
]
