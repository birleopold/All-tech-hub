from django.urls import path

from catalog import views

urlpatterns = [
    path("", views.ProductListView.as_view(), name="product_list"),
    path("item/<slug:slug>/", views.ProductDetailView.as_view(), name="product_detail"),
    path(
        "item/<slug:slug>/review/",
        views.product_review_submit,
        name="product_review_submit",
    ),
]
