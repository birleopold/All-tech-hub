from django.urls import path

from purchasing import views

urlpatterns = [
    path("purchasing/", views.PurchasingHomeView.as_view(), name="staff_purchasing"),
    path("purchasing/po/new/", views.PurchaseOrderCreateView.as_view(), name="staff_po_create"),
    path("purchasing/po/<int:pk>/", views.PurchaseOrderUpdateView.as_view(), name="staff_po_edit"),
    path("purchasing/po/<int:pk>/receive/", views.receive_stock, name="staff_po_receive"),
    path("purchasing/po/<int:pk>/return/", views.supplier_return, name="staff_po_return"),
]

