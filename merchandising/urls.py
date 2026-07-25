from django.urls import path

from merchandising.views import (
    BuyingGuideDetailView,
    BuyingGuideListView,
    CommercialLandingPageView,
    DeliveryZoneListView,
)


ROOT_PAGE_ROUTES = (
    "laptop-prices-in-uganda",
    "dell-laptops-uganda",
    "hp-laptops-uganda",
    "lenovo-laptops-uganda",
    "macbook-prices-in-uganda",
    "refurbished-laptops-uganda",
    "business-laptops-uganda",
    "student-laptops-uganda",
    "gaming-laptops-uganda",
    "desktop-computer-prices-in-uganda",
    "printer-prices-in-uganda",
    "wifi-router-prices-in-uganda",
)

urlpatterns = [
    path("guides/", BuyingGuideListView.as_view(), name="buying_guide_list"),
    path("guides/<slug:slug>/", BuyingGuideDetailView.as_view(), name="buying_guide_detail"),
    path("delivery-areas/", DeliveryZoneListView.as_view(), name="delivery_zones"),
    path("commercial/<slug:slug>/", CommercialLandingPageView.as_view(), name="commercial_landing"),
]

for route_slug in ROOT_PAGE_ROUTES:
    urlpatterns.append(
        path(
            f"{route_slug}/",
            CommercialLandingPageView.as_view(),
            {"slug": route_slug},
            name=f"commercial_{route_slug.replace('-', '_')}",
        )
    )
