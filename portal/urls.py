from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from billing.revision_comparison import customer_quote_revision_compare
from core import private_views
from loyalty import views as loyalty_views
from portal import views, warranty_views
from portal.forms import CustomerPortalAuthenticationForm, CustomerPortalPasswordResetForm

urlpatterns = [
    path("", views.PortalHomeView.as_view(), name="portal_home"),
    path("kb/", views.KnowledgeBaseListView.as_view(), name="portal_kb"),
    path("kb/<slug:slug>/", views.kb_article_detail, name="portal_kb_article"),
    path("signup/", views.CustomerSignUpView.as_view(), name="portal_signup"),
    path("verify-email/<str:token>/", views.verify_customer_email, name="portal_verify_email"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="portal/login.html",
            authentication_form=CustomerPortalAuthenticationForm,
        ),
        name="portal_login",
    ),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=CustomerPortalPasswordResetForm,
            template_name="portal/password_reset.html",
            email_template_name="portal/password_reset_email.txt",
            subject_template_name="portal/password_reset_subject.txt",
            success_url=reverse_lazy("portal_password_reset_done"),
        ),
        name="portal_password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="portal/password_reset_done.html",
        ),
        name="portal_password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="portal/password_reset_confirm.html",
            success_url=reverse_lazy("portal_password_reset_complete"),
        ),
        name="portal_password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="portal/password_reset_complete.html",
        ),
        name="portal_password_reset_complete",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="portal_logout"),
    path("jobs/", views.MyJobsView.as_view(), name="portal_jobs"),
    path("repair-request/", views.PortalRepairIntakeView.as_view(), name="portal_repair_intake"),
    path("jobs/<int:pk>/", views.my_job_detail, name="portal_job_detail"),
    path("jobs/<int:pk>/feedback/", views.job_feedback_view, name="portal_job_feedback"),
    path("jobs/<int:pk>/handover/signature/", private_views.portal_job_handover_signature, name="portal_job_handover_signature"),
    path(
        "jobs/attachments/<int:pk>/file/",
        private_views.portal_job_attachment,
        name="portal_job_attachment_file",
    ),
    path("orders/", views.MyOrdersView.as_view(), name="portal_orders"),
    path("orders/<int:pk>/", views.my_order_detail, name="portal_order_detail"),
    path("warranties/", warranty_views.customer_warranties, name="portal_warranties"),
    path("loyalty/", loyalty_views.portal_loyalty_account, name="portal_loyalty_account"),
    path(
        "preferences/",
        loyalty_views.portal_marketing_preferences,
        name="portal_marketing_preferences",
    ),
    path("documents/", views.MyDocumentsView.as_view(), name="portal_documents"),
    path("documents/<int:pk>/revisions/<int:revision_number>/", customer_quote_revision_compare, name="portal_quote_revision_compare"),
    path("documents/<int:pk>/pdf/", views.my_document_pdf, name="portal_document_pdf"),
    path("documents/<int:pk>/pay/", views.my_document_payment, name="portal_document_payment"),
    path("tickets/", views.MyTicketsView.as_view(), name="portal_tickets"),
    path("tickets/new/", views.PortalTicketCreateView.as_view(), name="portal_ticket_create"),
    path("tickets/<int:pk>/", views.my_ticket_detail, name="portal_ticket_detail"),
    path(
        "tickets/comments/<int:pk>/attachment/",
        private_views.portal_ticket_attachment,
        name="portal_ticket_attachment",
    ),
    path("addresses/", views.my_addresses, name="portal_addresses"),
    path("addresses/<int:pk>/edit/", views.my_address_edit, name="portal_address_edit"),
    path("wishlist/", views.my_wishlist, name="portal_wishlist"),
    path("wishlist/add/<int:product_id>/", views.wishlist_add, name="portal_wishlist_add"),
    path("wishlist/remove/<int:product_id>/", views.wishlist_remove, name="portal_wishlist_remove"),
]
