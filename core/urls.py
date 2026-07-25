from django.urls import path
from django.views.generic import RedirectView

from core import views
from core.public_service_worker import service_worker
from core.public_views import public_contact_view
from merchandising.catalog_views import MerchandisedHomeView

urlpatterns = [
    path("", MerchandisedHomeView.as_view(), name="home"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    path("service-worker.js", service_worker, name="service_worker"),
    path("about/", views.AboutView.as_view(), name="about"),
    path(
        "buying-guide/",
        RedirectView.as_view(pattern_name="buying_guide_list", permanent=True),
        name="buying_guide",
    ),
    path("contact/", public_contact_view, name="contact"),
]
