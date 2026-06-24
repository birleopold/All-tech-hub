from django.urls import path

from reports import views

urlpatterns = [
    path("reports/", views.ReportsHomeView.as_view(), name="staff_reports"),
    path(
        "reports/export/orders.csv",
        views.staff_export_orders_csv,
        name="staff_export_orders_csv",
    ),
    path(
        "reports/export/jobs.csv",
        views.staff_export_jobs_csv,
        name="staff_export_jobs_csv",
    ),
    path(
        "reports/export/tickets.csv",
        views.staff_export_tickets_csv,
        name="staff_export_tickets_csv",
    ),
    path(
        "reports/export/low-stock.csv",
        views.staff_export_low_stock_csv,
        name="staff_export_low_stock_csv",
    ),
    path(
        "reports/export/documents.csv",
        views.staff_export_documents_csv,
        name="staff_export_documents_csv",
    ),
]

