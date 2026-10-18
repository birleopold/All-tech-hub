"""Lead attribution diagnostics must never mutate customer enquiries."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from marketing.models import MarketingLead


class LeadAttributionReportTests(TestCase):
    def test_report_is_read_only_and_retains_direct_as_recorded(self):
        lead = MarketingLead.objects.create(name="Attribution test", source="direct")
        output = StringIO()
        call_command("report_lead_attribution", days=90, stdout=output)
        self.assertIn("direct: 1", output.getvalue())
        lead.refresh_from_db()
        self.assertEqual(lead.source, "direct")
        self.assertIsNone(lead.assigned_to_id)
