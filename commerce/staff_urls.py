from django.urls import path

from commerce import staff_views
from commerce.staff_order_list_view import StaffOrderListView

urlpatterns = [
    path("orders/", StaffOrderListView.as_view(), name="staff_orders"),
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
    path(
        "orders/<int:pk>/return/",
        staff_views.staff_customer_return,
        name="staff_order_return",
    ),
    path(
        "orders/<int:pk>/status/",
        staff_views.staff_order_transition,
        name="staff_order_transition",
    ),
    path(
        "orders/<int:pk>/shipment/",
        staff_views.staff_order_shipment,
        name="staff_order_shipment",
    ),
]
