from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from marketing.forms import MarketingLeadForm
from marketing.models import MarketingLead


class MarketingLeadFollowUpTests(TestCase):
    def test_first_contact_and_win_timestamps_follow_status(self):
        lead = MarketingLead.objects.create(name="Kampala lead", source="whatsapp")
        self.assertIsNone(lead.first_contacted_at)
        lead.status = MarketingLead.STATUS_CONTACTED
        lead.save()
        self.assertIsNotNone(lead.first_contacted_at)
        first_contact = lead.first_contacted_at
        lead.status = MarketingLead.STATUS_WON
        lead.next_follow_up_at = timezone.now() + timedelta(days=1)
        lead.save()
        self.assertEqual(lead.first_contacted_at, first_contact)
        self.assertIsNotNone(lead.won_at)
        self.assertIsNone(lead.next_follow_up_at)

    def test_overdue_follow_up_excludes_closed_leads(self):
        lead = MarketingLead.objects.create(
            name="Follow-up lead",
            source="tiktok",
            status=MarketingLead.STATUS_CONTACTED,
            next_follow_up_at=timezone.now() - timedelta(minutes=5),
        )
        self.assertTrue(lead.follow_up_overdue)
        lead.status = MarketingLead.STATUS_LOST
        lead.save()
        self.assertFalse(lead.follow_up_overdue)

    def test_lead_form_accepts_local_follow_up_time(self):
        future = timezone.localtime(timezone.now() + timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        form = MarketingLeadForm(
            data={
                "name": "Campaign enquiry",
                "email": "lead@example.com",
                "phone": "0700000000",
                "source": "instagram",
                "medium": "social",
                "status": MarketingLead.STATUS_NEW,
                "estimated_value": "1500000",
                "next_follow_up_at": future,
                "notes": "Interested in a business laptop.",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_status_only_save_persists_automatic_contact_timestamp(self):
        lead = MarketingLead.objects.create(name="Status-only lead", source="whatsapp")
        lead.status = MarketingLead.STATUS_CONTACTED

        lead.save(update_fields=["status"])
        lead.refresh_from_db()

        self.assertIsNotNone(lead.first_contacted_at)

    def test_first_contact_clears_initial_response_follow_up(self):
        due_at = timezone.now() + timedelta(minutes=30)
        lead = MarketingLead.objects.create(
            name="Timed lead",
            source="website",
            response_due_at=due_at,
            next_follow_up_at=due_at,
        )
        lead.status = MarketingLead.STATUS_CONTACTED

        lead.save(update_fields=["status"])
        lead.refresh_from_db()

        self.assertIsNotNone(lead.first_contacted_at)
        self.assertIsNone(lead.next_follow_up_at)

    def test_overdue_response_is_detected_before_first_contact(self):
        lead = MarketingLead.objects.create(
            name="Late lead",
            source="website",
            response_due_at=timezone.now() - timedelta(minutes=1),
        )

        self.assertTrue(lead.response_overdue)
        lead.status = MarketingLead.STATUS_CONTACTED
        lead.save()
        self.assertFalse(lead.response_overdue)
