from django.contrib.auth.decorators import user_passes_test
from django.urls import path

from growth import views

staff_only = user_passes_test(
    lambda user: user.is_authenticated and user.is_staff
)

urlpatterns = [
    path("", views.GrowthDashboardView.as_view(), name="staff_growth_dashboard"),
    path("settings/", views.GrowthSettingsUpdateView.as_view(), name="staff_growth_settings"),
    path("products/", views.ProductMetadataListView.as_view(), name="staff_growth_product_metadata"),
    path("products/new/", views.ProductMetadataCreateView.as_view(), name="staff_growth_product_metadata_create"),
    path("products/<int:pk>/edit/", views.ProductMetadataUpdateView.as_view(), name="staff_growth_product_metadata_edit"),
    path("groups/", views.DistributionGroupListView.as_view(), name="staff_growth_distribution_groups"),
    path("groups/new/", views.DistributionGroupCreateView.as_view(), name="staff_growth_distribution_create"),
    path("groups/<int:pk>/edit/", views.DistributionGroupUpdateView.as_view(), name="staff_growth_distribution_edit"),
    path("ambassadors/", views.AmbassadorListView.as_view(), name="staff_growth_ambassadors"),
    path("ambassadors/new/", views.AmbassadorCreateView.as_view(), name="staff_growth_ambassador_create"),
    path("ambassadors/<int:pk>/edit/", views.AmbassadorUpdateView.as_view(), name="staff_growth_ambassador_edit"),
    path("ambassadors/<int:pk>/qr/", views.ambassador_qr, name="staff_growth_ambassador_qr"),
    path("ambassadors/conversions/", views.AmbassadorConversionListView.as_view(), name="staff_growth_ambassador_conversions"),
    path("ambassadors/conversions/<int:pk>/approve/", views.AmbassadorConversionApproveView.as_view(), name="staff_growth_conversion_approve"),
    path("ambassadors/conversions/<int:pk>/pay/", views.AmbassadorConversionPayView.as_view(), name="staff_growth_conversion_pay"),
    path("content/", staff_only(views.content_asset_workspace), name="staff_growth_content_assets"),
    path(
        "content/images/<int:pk>/<str:format_name>/",
        staff_only(views.content_marketing_image_download),
        name="staff_growth_content_image",
    ),
    path("saved-carts/", views.SavedCartListView.as_view(), name="staff_growth_saved_carts"),
    path("stock-alerts/", views.StockAlertListView.as_view(), name="staff_growth_stock_alerts"),
]
