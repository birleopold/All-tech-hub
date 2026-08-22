from django.urls import path

from purchasing import views, workspace_views

urlpatterns = [
    path("purchasing/", workspace_views.PurchasingWorkspaceHomeView.as_view(), name="staff_purchasing"),
    path("purchasing/po/new/", views.PurchaseOrderCreateView.as_view(), name="staff_po_create"),
    path("purchasing/replenish/<int:pk>/", workspace_views.ReplenishmentPurchaseOrderView.as_view(), name="staff_replenishment_create_po"),
    path("purchasing/po/<int:pk>/", views.PurchaseOrderUpdateView.as_view(), name="staff_po_edit"),
    path("purchasing/po/<int:pk>/receive/", views.receive_stock, name="staff_po_receive"),
    path("purchasing/po/<int:pk>/return/", views.supplier_return, name="staff_po_return"),
]
