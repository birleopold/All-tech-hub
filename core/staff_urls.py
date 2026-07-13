from django.urls import path

from core import staff_views

urlpatterns = [
    path("search/", staff_views.StaffGlobalSearchView.as_view(), name="staff_search"),
    path(
        "security/",
        staff_views.SecurityDiagnosticsView.as_view(),
        name="staff_security_diagnostics",
    ),
    path("audit/", staff_views.AuditEventListView.as_view(), name="staff_audit_log"),
    path("tickets/", staff_views.SupportTicketListView.as_view(), name="staff_tickets"),
    path("tickets/new/", staff_views.SupportTicketCreateView.as_view(), name="staff_ticket_create"),
    path("tickets/<int:pk>/", staff_views.SupportTicketDetailView.as_view(), name="staff_ticket_detail"),
    path("tickets/<int:pk>/edit/", staff_views.SupportTicketUpdateView.as_view(), name="staff_ticket_edit"),
    path(
        "tickets/<int:pk>/comments/",
        staff_views.TicketCommentCreateView.as_view(),
        name="staff_ticket_comment_create",
    ),
    path("notifications/", staff_views.StaffNotificationListView.as_view(), name="staff_notifications"),
    path(
        "notifications/<int:pk>/go/",
        staff_views.StaffNotificationGoView.as_view(),
        name="staff_notification_go",
    ),
    path(
        "notifications/read-all/",
        staff_views.MarkNotificationsReadView.as_view(),
        name="staff_notifications_read_all",
    ),
    path("saved-search/save/", staff_views.SaveStaffSearchView.as_view(), name="staff_save_search"),
    path(
        "saved-search/<int:pk>/delete/",
        staff_views.DeleteStaffSearchView.as_view(),
        name="staff_delete_saved_search",
    ),
    path("contact/", staff_views.ContactMessageListView.as_view(), name="staff_contact_messages"),
    path(
        "contact/<int:pk>/toggle/",
        staff_views.ContactMessageToggleView.as_view(),
        name="staff_contact_toggle",
    ),
    path(
        "contact/<int:pk>/to-ticket/",
        staff_views.ContactMessageConvertTicketView.as_view(),
        name="staff_contact_to_ticket",
    ),
    path(
        "business-hours/",
        staff_views.BusinessHoursView.as_view(),
        name="staff_business_hours",
    ),
]
