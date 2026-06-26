from django.urls import path

from inventory import views

urlpatterns = [
    path("inventory/", views.InventoryHomeView.as_view(), name="staff_inventory"),
    path(
        "inventory/movements/",
        views.StockMovementListView.as_view(),
        name="staff_stock_movements",
    ),
    path(
        "inventory/warranty/",
        views.WarrantyCenterView.as_view(),
        name="staff_warranty_center",
    ),
    path("inventory/adjust/", views.create_stock_adjustment, name="staff_stock_adjust"),
    path(
        "inventory/jobs/<int:job_pk>/part/",
        views.job_record_part_usage,
        name="staff_job_stock_use",
    ),
    path("inventory/products/", views.ProductManageListView.as_view(), name="staff_products"),
    path("inventory/products/new/", views.ProductCreateView.as_view(), name="staff_product_create"),
    path("inventory/products/<int:pk>/", views.ProductUpdateView.as_view(), name="staff_product_edit"),
    path("inventory/products/<int:pk>/labels/", views.product_label_sheet, name="staff_product_labels"),
    path("inventory/serials/<int:pk>/labels/", views.serial_label_sheet, name="staff_serial_labels"),
    path("inventory/stocktake/", views.StockTakeListView.as_view(), name="staff_stocktakes"),
    path("inventory/stocktake/new/", views.stocktake_create, name="staff_stocktake_create"),
    path("inventory/stocktake/<int:pk>/", views.StockTakeDetailView.as_view(), name="staff_stocktake_detail"),
    path("inventory/stocktake/<int:pk>/labels/", views.stocktake_label_sheet, name="staff_stocktake_labels"),
    path("inventory/stocktake/<int:pk>/lines/", views.stocktake_add_line, name="staff_stocktake_add_line"),
    path("inventory/stocktake/<int:pk>/post/", views.stocktake_post, name="staff_stocktake_post"),
]

