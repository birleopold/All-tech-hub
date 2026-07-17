from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import TemplateView

from loyalty.reporting import customer_growth_summary


class CustomerGrowthDashboardView(UserPassesTestMixin, TemplateView):
    template_name = "loyalty/staff_customer_growth.html"

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        channel = (self.request.GET.get("channel") or "email").strip().lower()
        segment = (self.request.GET.get("segment") or "all").strip().lower()
        topic = (self.request.GET.get("topic") or "product_updates").strip().lower()
        context.update(customer_growth_summary(channel=channel, segment=segment, topic=topic))
        return context
