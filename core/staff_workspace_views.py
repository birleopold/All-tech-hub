from django.db.models import Count, Q

from core import staff_views
from core.models import AuditEvent, ContactMessage, StaffNotification, SupportTicket
from marketing.models import MarketingLead


class SupportTicketWorkspaceListView(staff_views.SupportTicketListView):
    """Support queue with consistent operational metrics and pagination state."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        open_statuses = [SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS]
        open_tickets = list(
            SupportTicket.objects.filter(status__in=open_statuses).only(
                "id", "status", "priority", "created_at"
            )
        )
        stats = SupportTicket.objects.aggregate(
            total=Count("pk"),
            open=Count("pk", filter=Q(status=SupportTicket.STATUS_OPEN)),
            in_progress=Count("pk", filter=Q(status=SupportTicket.STATUS_IN_PROGRESS)),
            urgent=Count(
                "pk",
                filter=Q(
                    status__in=open_statuses,
                    priority=SupportTicket.PRIORITY_URGENT,
                ),
            ),
        )
        stats["overdue"] = sum(1 for ticket in open_tickets if ticket.is_overdue)
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(
            {
                "ticket_stats": stats,
                "querystring": params.urlencode(),
            }
        )
        return context


class ContactMessageWorkspaceListView(staff_views.ContactMessageListView):
    """Contact inbox with handled/unhandled summary and stable pagination."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contact_stats"] = ContactMessage.objects.aggregate(
            total=Count("pk"),
            unhandled=Count("pk", filter=Q(handled=False)),
            handled=Count("pk", filter=Q(handled=True)),
        )
        visible_messages = list(context.get("messages_list", ()))
        linked_leads = {
            lead.contact_message_id: lead
            for lead in MarketingLead.objects.filter(
                contact_message_id__in=[message.pk for message in visible_messages]
            ).select_related("assigned_to", "campaign", "product")
        }
        for message in visible_messages:
            message.sales_lead = linked_leads.get(message.pk)
        context["contact_stats"]["unassigned_leads"] = MarketingLead.objects.filter(
            status=MarketingLead.STATUS_NEW,
            assigned_to__isnull=True,
        ).count()
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()
        return context


class StaffNotificationWorkspaceListView(staff_views.StaffNotificationListView):
    """Personal notification centre with read-state summary."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        own = StaffNotification.objects.filter(recipient=self.request.user)
        context["notification_stats"] = own.aggregate(
            total=Count("pk"),
            unread=Count("pk", filter=Q(is_read=False)),
            read=Count("pk", filter=Q(is_read=True)),
        )
        return context


class AuditWorkspaceListView(staff_views.AuditEventListView):
    """Audit trail with total volume and filter-safe pagination."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["audit_total"] = AuditEvent.objects.count()
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()
        return context
