from django.urls import path
from django.views.generic import TemplateView

from core import views
from core.public_service_worker import service_worker
from core.public_views import PublicHomeView, public_contact_view

urlpatterns = [
    path("", PublicHomeView.as_view(), name="home"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    path("service-worker.js", service_worker, name="service_worker"),
    path("about/", views.AboutView.as_view(), name="about"),
    path(
        "buying-guide/",
        TemplateView.as_view(template_name="core/seo_buying_guide.html"),
        name="buying_guide",
    ),
    path("contact/", public_contact_view, name="contact"),
]
