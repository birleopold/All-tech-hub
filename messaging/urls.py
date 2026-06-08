from django.urls import path

from messaging import views

urlpatterns = [
    path("email/document/<int:pk>/", views.email_document, name="staff_email_document"),
    path("email/job/<int:pk>/", views.email_jobcard, name="staff_email_jobcard"),
    path("email/job/<int:pk>/update/", views.email_job_update, name="staff_email_job_update"),
    path("email/log/", views.EmailLogListView.as_view(), name="staff_email_log"),
    path("email/log/<int:pk>/", views.email_log_detail, name="staff_email_log_detail"),
    path("email/log/<int:pk>/retry/", views.email_log_retry, name="staff_email_log_retry"),
]

