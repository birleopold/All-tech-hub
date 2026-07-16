from django.contrib.auth import views as auth_views
from django.urls import path

from core import private_views
from portal import views

urlpatterns = [
    path("", views.PortalHomeView.as_view(), name="portal_home"),
    path("kb/", views.KnowledgeBaseListView.as_view(), name="portal_kb"),
    path("kb/<slug:slug>/", views.kb_article_detail, name="portal_kb_article"),
    path("signup/", views.CustomerSignUpView.as_view(), name="portal_signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="portal/login.html"),
        name="portal_login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="portal_logout"),
    path("jobs/", views.MyJobsView.as_view(), name="portal_jobs"),
    path("repair-request/", views.PortalRepairIntakeView.as_view(), name="portal_repair_intake"),
    path("jobs/<int:pk>/", views.my_job_detail, name="portal_job_detail"),
    path("jobs/<int:pk>/feedback/", views.job_feedback_view, name="portal_job_feedback"),
    path(
        "jobs/attachments/<int:pk>/file/",
        private_views.portal_job_attachment,
        name="portal_job_attachment_file",
    ),
    path("orders/", views.MyOrdersView.as_view(), name="portal_orders"),
    path("orders/<int:pk>/", views.my_order_detail, name="portal_order_detail"),
    path("documents/", views.MyDocumentsView.as_view(), name="portal_documents"),
    path("documents/<int:pk>/pdf/", views.my_document_pdf, name="portal_document_pdf"),
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
