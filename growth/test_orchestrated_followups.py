from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from automation.models import AutomationControl
from core.models import StaffNotification
from marketing.models import MarketingLead


class OrchestratedLeadFollowUpTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="lead-orchestrator", password="pw", is_staff=True
        )
        self.lead = MarketingLead.objects.create(
            name="Interested Kampala customer",
            source="website",
            assigned_to=self.owner,
        )
        MarketingLead.objects.filter(pk=self.lead.pk).update(
            response_due_at=timezone.now() - timedelta(minutes=60),
            next_follow_up_at=timezone.now() - timedelta(minutes=60),
            last_reminded_at=None,
        )

    def test_production_worker_processes_due_sales_followups(self):
        output = StringIO()
        call_command("run_growth_automation", limit=5, stdout=output)
        self.lead.refresh_from_db()
        self.assertIsNotNone(self.lead.last_reminded_at)
        self.assertTrue(
            StaffNotification.objects.filter(
                recipient=self.owner, message__icontains="follow-up overdue"
            ).exists()
        )
        self.assertIn("lead reminders: 1", output.getvalue())

    def test_dry_run_does_not_change_sales_followup(self):
        call_command("run_growth_automation", limit=5, dry_run=True)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.last_reminded_at)

    def test_paused_automation_does_not_send_sales_followup(self):
        control = AutomationControl.load()
        control.is_paused = True
        control.save(update_fields=["is_paused", "updated_at"])
        call_command("run_growth_automation", limit=5)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.last_reminded_at)
