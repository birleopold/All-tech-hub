from django.db.models import Count, Q

from billing import document_workflow_views
from billing.models import CommercialDocument


class StaffCommercialDocumentListView(document_workflow_views.CommercialDocumentListView):
    """Commercial-document list with summary metrics and stable pagination links."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = CommercialDocument.objects.aggregate(
            total=Count("pk"),
            drafts=Count("pk", filter=Q(status=CommercialDocument.STATUS_DRAFT)),
            outstanding=Count(
                "pk",
                filter=Q(
                    status__in=[
                        CommercialDocument.STATUS_ISSUED,
                        CommercialDocument.STATUS_PARTIALLY_PAID,
                    ]
                ),
            ),
            paid=Count("pk", filter=Q(status=CommercialDocument.STATUS_PAID)),
        )
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context.update(
            {
                "document_stats": stats,
                "querystring": query_params.urlencode(),
            }
        )
        return context
