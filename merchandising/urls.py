from django.urls import path

from merchandising.constants import ROOT_COMMERCIAL_SLUGS
from merchandising.views import (
    BuyingGuideDetailView,
    BuyingGuideListView,
    CommercialLandingPageView,
    DeliveryZoneListView,
)

urlpatterns = [
    path("guides/", BuyingGuideListView.as_view(), name="buying_guide_list"),
    path("guides/<slug:slug>/", BuyingGuideDetailView.as_view(), name="buying_guide_detail"),
    path("delivery-areas/", DeliveryZoneListView.as_view(), name="delivery_zones"),
    path("commercial/<slug:slug>/", CommercialLandingPageView.as_view(), name="commercial_landing"),
]

for route_slug in ROOT_COMMERCIAL_SLUGS:
    urlpatterns.append(
        path(
            f"{route_slug}/",
            CommercialLandingPageView.as_view(),
            {"slug": route_slug},
            name=f"commercial_{route_slug.replace('-', '_')}",
        )
    )
