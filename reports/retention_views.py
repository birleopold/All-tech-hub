from django.views.generic import TemplateView

from core.mixins import StaffRequiredMixin
from reports.retention import retention_summary


class RetentionDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "reports/retention_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            days = int(self.request.GET.get("days") or 90)
        except (TypeError, ValueError):
            days = 90
        context["retention"] = retention_summary(days)
        return context
