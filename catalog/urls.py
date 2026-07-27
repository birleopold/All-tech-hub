from django.urls import path

from catalog import views
from catalog.refined_public_views import public_catalog_suggestions
from merchandising.catalog_views import MerchandisedSEOProductListView
from merchandising.growth_views import GrowthProductDetailView

urlpatterns = [
    path("", MerchandisedSEOProductListView.as_view(), name="product_list"),
    path(
        "products/",
        MerchandisedSEOProductListView.as_view(),
        {"kind": "physical"},
        name="physical_product_list",
    ),
    path(
        "services/",
        MerchandisedSEOProductListView.as_view(),
        {"kind": "service"},
        name="service_list",
    ),
    path(
        "category/<slug:category_slug>/",
        MerchandisedSEOProductListView.as_view(),
        name="product_category",
    ),
    path(
        "collection/<slug:collection_slug>/",
        MerchandisedSEOProductListView.as_view(),
        name="product_collection",
    ),
    path(
        "brand/<slug:brand_slug>/",
        MerchandisedSEOProductListView.as_view(),
        name="product_brand",
    ),
    path("suggestions/", public_catalog_suggestions, name="catalog_suggestions"),
    path("compare/", views.product_compare, name="product_compare"),
    path("compare/clear/", views.product_compare_clear, name="product_compare_clear"),
    path(
        "compare/<int:product_id>/toggle/",
        views.product_compare_toggle,
        name="product_compare_toggle",
    ),
    path(
        "item/<slug:slug>/",
        GrowthProductDetailView.as_view(
            template_name="catalog/seo_product_detail.html"
        ),
        name="product_detail",
    ),
    path(
        "item/<slug:slug>/review/",
        views.product_review_submit,
        name="product_review_submit",
    ),
]
