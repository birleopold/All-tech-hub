from django.db.models import Count, Q

from messaging import views
from messaging.models import OutboundEmail


class EmailWorkspaceListView(views.EmailLogListView):
    """Email evidence ledger with delivery and failure summaries."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        failure_statuses = [
            OutboundEmail.STATUS_FAILED,
            OutboundEmail.STATUS_SOFT_BOUNCED,
            OutboundEmail.STATUS_BOUNCED,
            OutboundEmail.STATUS_COMPLAINED,
        ]
        context["email_stats"] = OutboundEmail.objects.aggregate(
            total=Count("pk"),
            delivered=Count("pk", filter=Q(status=OutboundEmail.STATUS_DELIVERED)),
            accepted=Count("pk", filter=Q(status=OutboundEmail.STATUS_SENT)),
            failed=Count("pk", filter=Q(status__in=failure_statuses)),
            suppressed=Count("pk", filter=Q(status=OutboundEmail.STATUS_SUPPRESSED)),
        )
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()
        return context
