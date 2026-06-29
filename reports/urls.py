from django.urls import path

from reports import commission_views, views

urlpatterns = [
    path("reports/", commission_views.ReportsHomeView.as_view(), name="staff_reports"),
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
        commission_views.staff_export_documents_csv,
        name="staff_export_documents_csv",
    ),
    path(
        "reports/export/stock-velocity.csv",
        views.staff_export_stock_velocity_csv,
        name="staff_export_stock_velocity_csv",
    ),
    path(
        "reports/export/payment-exceptions.csv",
        views.staff_export_payment_exceptions_csv,
        name="staff_export_payment_exceptions_csv",
    ),
    path(
        "reports/export/customer-value.csv",
        commission_views.staff_export_customer_value_csv,
        name="staff_export_customer_value_csv",
    ),
    path(
        "reports/export/margin-lines.csv",
        commission_views.staff_export_margin_lines_csv,
        name="staff_export_margin_lines_csv",
    ),
    path(
        "reports/export/partner-payables.csv",
        commission_views.staff_export_partner_payables_csv,
        name="staff_export_partner_payables_csv",
    ),
]
