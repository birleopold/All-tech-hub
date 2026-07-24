from django.urls import path

from core import views
from core.public_views import PublicHomeView

urlpatterns = [
    path("", PublicHomeView.as_view(), name="home"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("contact/", views.contact_view, name="contact"),
]
