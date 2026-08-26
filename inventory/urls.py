from django.urls import path

from inventory import product_photo_views, views
from inventory.catalog_workspace_views import ProductWorkspaceListView, StockTakeWorkspaceListView
from inventory.inventory_home_view import StaffInventoryHomeView
from merchandising.staff_views import (
    CatalogueBulkEnrichmentView,
    ProductCommercialReviewView,
)

urlpatterns = [
    path("inventory/push/public-key/", product_photo_views.push_public_key, name="staff_push_public_key"),
    path("inventory/push/subscribe/", product_photo_views.save_push_subscription, name="staff_push_subscribe"),
    path("inventory/products/<int:product_id>/photos/phone/", product_photo_views.start_product_photo_session, name="staff_product_photo_start"),
    path("inventory/product-photos/<str:token>/", product_photo_views.product_photo_mobile, name="staff_product_photo_mobile"),
    path("inventory/product-photos/<str:token>/upload/", product_photo_views.product_photo_upload, name="staff_product_photo_upload"),
    path("inventory/product-photos/<str:token>/status/", product_photo_views.product_photo_status, name="staff_product_photo_status"),
    path("inventory/product-photos/<str:token>/qr/", product_photo_views.product_photo_qr, name="staff_product_photo_qr"),
    path("inventory/", StaffInventoryHomeView.as_view(), name="staff_inventory"),
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
    path("inventory/products/", ProductWorkspaceListView.as_view(), name="staff_products"),
    path(
        "inventory/catalogue-enrichment/",
        CatalogueBulkEnrichmentView.as_view(),
        name="staff_catalogue_bulk_enrichment",
    ),
    path("inventory/products/new/", views.ProductCreateView.as_view(), name="staff_product_create"),
    path(
        "inventory/products/<int:pk>/commercial/",
        ProductCommercialReviewView.as_view(),
        name="staff_product_commercial_review",
    ),
    path("inventory/products/<int:pk>/", views.ProductUpdateView.as_view(), name="staff_product_edit"),
    path("inventory/products/<int:pk>/labels/", views.product_label_sheet, name="staff_product_labels"),
    path("inventory/serials/<int:pk>/labels/", views.serial_label_sheet, name="staff_serial_labels"),
    path("inventory/stocktake/", StockTakeWorkspaceListView.as_view(), name="staff_stocktakes"),
    path("inventory/stocktake/new/", views.stocktake_create, name="staff_stocktake_create"),
    path("inventory/stocktake/<int:pk>/", views.StockTakeDetailView.as_view(), name="staff_stocktake_detail"),
    path("inventory/stocktake/<int:pk>/labels/", views.stocktake_label_sheet, name="staff_stocktake_labels"),
    path("inventory/stocktake/<int:pk>/lines/", views.stocktake_add_line, name="staff_stocktake_add_line"),
    path("inventory/stocktake/<int:pk>/post/", views.stocktake_post, name="staff_stocktake_post"),
]
