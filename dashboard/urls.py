from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.StaffDashboardView.as_view(), name="staff_dashboard"),
]
