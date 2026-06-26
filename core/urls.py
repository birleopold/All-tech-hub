from django.urls import path

from core import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("healthz/", views.healthz, name="healthz"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("contact/", views.contact_view, name="contact"),
]
