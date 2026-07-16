from django.views.generic import TemplateView

from core.mixins import StaffRequiredMixin
from reports.conversion import conversion_summary


class ConversionLifecycleView(StaffRequiredMixin, TemplateView):
    template_name = "reports/conversion_lifecycle.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_days = self.request.GET.get("days") or "30"
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 30
        context["conversion"] = conversion_summary(days)
        return context
