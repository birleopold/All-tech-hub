from django.urls import path

from billing import views

urlpatterns = [
    path("documents/", views.CommercialDocumentListView.as_view(), name="staff_documents"),
    path(
        "documents/<int:pk>/quote-approve/",
        views.quote_internal_approve,
        name="staff_document_quote_approve",
    ),
    path(
        "documents/<int:pk>/quote-customer-link/",
        views.quote_enable_customer_acceptance,
        name="staff_document_quote_customer_link",
    ),
    path(
        "documents/new/",
        views.CommercialDocumentCreateView.as_view(),
        name="staff_document_create",
    ),
    path(
        "documents/<int:pk>/",
        views.CommercialDocumentUpdateView.as_view(),
        name="staff_document_edit",
    ),
    path(
        "documents/<int:pk>/view/",
        views.CommercialDocumentDetailView.as_view(),
        name="staff_document_view",
    ),
    path("documents/<int:pk>/pdf/", views.document_pdf_view, name="staff_document_pdf"),
    path(
        "documents/<int:pk>/payment/",
        views.document_record_payment,
        name="staff_document_payment",
    ),
    path(
        "documents/<int:pk>/to-proforma/",
        views.convert_document,
        {"target": "proforma"},
        name="staff_document_to_proforma",
    ),
    path(
        "documents/<int:pk>/to-delivery-note/",
        views.convert_document,
        {"target": "delivery-note"},
        name="staff_document_to_delivery_note",
    ),
    path(
        "documents/<int:pk>/to-demand-note/",
        views.convert_document,
        {"target": "demand-note"},
        name="staff_document_to_demand_note",
    ),
    path(
        "documents/<int:pk>/to-receipt/",
        views.convert_document,
        {"target": "receipt"},
        name="staff_document_to_receipt",
    ),
    path(
        "documents/<int:pk>/to-invoice/",
        views.convert_document,
        {"target": "invoice"},
        name="staff_document_to_invoice",
    ),
]
