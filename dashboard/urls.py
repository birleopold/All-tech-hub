from django.urls import path

from dashboard import views
from merchandising import staff_views as merchandising_staff_views
from merchandising.campaign_views import staff_homepage_promotions

urlpatterns = [
    path("", views.StaffDashboardView.as_view(), name="staff_dashboard"),
    path(
        "catalogue-quality/",
        views.CatalogueQualityView.as_view(),
        name="staff_catalogue_quality",
    ),
    path(
        "catalogue-quality/<int:pk>/commercial-review/",
        merchandising_staff_views.ProductCommercialReviewView.as_view(),
        name="staff_product_commercial_review",
    ),
    path("seo/", views.SEOControlCenterView.as_view(), name="staff_seo"),
    path("homepage-campaigns/", staff_homepage_promotions, name="staff_homepage_promotions"),
    path("homepage-campaigns/<int:pk>/", staff_homepage_promotions, name="staff_homepage_promotion_edit"),
]
