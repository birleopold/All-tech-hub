from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.StaffDashboardView.as_view(), name="staff_dashboard"),
    path(
        "catalogue-quality/",
        views.CatalogueQualityView.as_view(),
        name="staff_catalogue_quality",
    ),
    path("seo/", views.SEOControlCenterView.as_view(), name="staff_seo"),
]
