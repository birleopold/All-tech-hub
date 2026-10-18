"""Safety tests for bounded bulk claiming of overdue leads."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from marketing.models import MarketingLead


class BatchClaimTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="bulk-lead-staff", password="local-test", is_staff=True
        )
        self.other = get_user_model().objects.create_user(
            username="bulk-lead-other", password="local-test", is_staff=True
        )

    def _lead(self, name, **kwargs):
        return MarketingLead.objects.create(name=name, **kwargs)

    def test_only_overdue_unassigned_open_leads_are_claimed(self):
        yesterday = timezone.now() - timedelta(days=1)
        tomorrow = timezone.now() + timedelta(days=1)
        overdue = self._lead("Overdue", next_follow_up_at=yesterday)
        assigned = self._lead("Already assigned", next_follow_up_at=yesterday,
                              assigned_to=self.other)
        upcoming = self._lead("Upcoming", next_follow_up_at=tomorrow)
        closed = self._lead("Closed", next_follow_up_at=yesterday,
                            status=MarketingLead.STATUS_WON)
        self.client.force_login(self.staff)
        result = self.client.post(reverse("staff_marketing_claim_overdue"))
        self.assertEqual(result.status_code, 302)
        for lead in (overdue, assigned, upcoming, closed):
            lead.refresh_from_db()
        self.assertEqual(overdue.assigned_to, self.staff)
        self.assertEqual(assigned.assigned_to, self.other)
        self.assertIsNone(upcoming.assigned_to)
        self.assertIsNone(closed.assigned_to)

    def test_claim_is_capped_at_25(self):
        yesterday = timezone.now() - timedelta(days=1)
        for i in range(31):
            self._lead(f"Overdue #{i}", next_follow_up_at=yesterday)
        self.client.force_login(self.staff)
        self.client.post(reverse("staff_marketing_claim_overdue"))
        self.assertEqual(MarketingLead.objects.filter(assigned_to=self.staff).count(), 25)

    def test_anonymous_get_cannot_claim(self):
        yesterday = timezone.now() - timedelta(days=1)
        lead = self._lead("Untouched", next_follow_up_at=yesterday)
        self.client.get(reverse("staff_marketing_claim_overdue"))
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_to)
