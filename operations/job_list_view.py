from django.db.models import Count, Q

from core.filters import apply_job_filters
from operations import views
from operations.models import JobCard


class StaffJobCardListView(views.JobCardListView):
    """Job-card queue with summary metrics and filter-safe pagination."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = JobCard.objects.all()
        stats = base.aggregate(
            total=Count("pk"),
            open=Count(
                "pk",
                filter=~Q(
                    status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
                ),
            ),
            scheduled=Count(
                "pk",
                filter=Q(scheduled_for__isnull=False)
                & ~Q(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]),
            ),
            urgent=Count(
                "pk",
                filter=Q(priority=JobCard.PRIORITY_URGENT)
                & ~Q(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]),
            ),
        )
        stats["overdue"] = apply_job_filters(base, {"due": "overdue"}).count()
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context.update(
            {
                "job_stats": stats,
                "querystring": query_params.urlencode(),
            }
        )
        return context
