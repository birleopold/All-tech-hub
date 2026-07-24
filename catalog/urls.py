from django.urls import path

from catalog import views
from catalog.detail_views import PublicProductDetailView
from catalog.public_views import PublicProductListView, public_catalog_suggestions

urlpatterns = [
    path("", PublicProductListView.as_view(), name="product_list"),
    path("suggestions/", public_catalog_suggestions, name="catalog_suggestions"),
    path("compare/", views.product_compare, name="product_compare"),
    path("compare/clear/", views.product_compare_clear, name="product_compare_clear"),
    path(
        "compare/<int:product_id>/toggle/",
        views.product_compare_toggle,
        name="product_compare_toggle",
    ),
    path("item/<slug:slug>/", PublicProductDetailView.as_view(), name="product_detail"),
    path(
        "item/<slug:slug>/review/",
        views.product_review_submit,
        name="product_review_submit",
    ),
]
