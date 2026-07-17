from django.urls import path

from commerce import retention_views, views

urlpatterns = [
    path("", views.cart_view, name="cart"),
    path("add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("update/", views.cart_update, name="cart_update"),
    path("remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("coupon/apply/", views.cart_apply_coupon, name="cart_apply_coupon"),
    path("coupon/remove/", views.cart_remove_coupon, name="cart_remove_coupon"),
    path("checkout/", views.checkout_view, name="checkout"),
    path(
        "order/<str:reference>/<uuid:view_key>/",
        views.order_detail,
        name="order_detail",
    ),
    path(
        "order/<str:reference>/<uuid:view_key>/reorder/",
        retention_views.order_reorder,
        name="order_reorder",
    ),
    path(
        "order/<str:reference>/<uuid:view_key>/review/<int:product_id>/",
        retention_views.order_product_review,
        name="order_product_review",
    ),
]
