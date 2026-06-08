from django.urls import path

from commerce import staff_views

urlpatterns = [
    path("orders/", staff_views.StaffOrderListView.as_view(), name="staff_orders"),
    path(
        "orders/<int:pk>/",
        staff_views.StaffOrderDetailView.as_view(),
        name="staff_order_detail",
    ),
    path(
        "orders/<int:pk>/invoice/",
        staff_views.staff_create_invoice_from_order,
        name="staff_order_invoice",
    ),
]
