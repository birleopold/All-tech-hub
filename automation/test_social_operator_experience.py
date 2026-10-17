"""Phase 7: staff controls show only owned posts and never guess channel reachability."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from automation.models import (
    PostAutomationPlan, PostChannelDelivery, SocialAutopilotSettings,
)
from marketing.models import ScheduledPost


class SocialOperatorExperienceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="social-operator-phase7",
            password="test-password",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.manager)
        self.settings = SocialAutopilotSettings.load()
        self.settings.enabled = False
        self.settings.channels = []
        self.settings.save()

    @patch("automation.staff_views.diagnose_channel")
    def test_empty_channel_selection_does_not_test_unselected_accounts(self, probe):
        response = self.client.post(
            reverse("staff_social_autopilot_test_connections")
        )
        self.assertEqual(response.status_code, 302)
        probe.assert_not_called()

    @patch("automation.staff_views.diagnose_channel")
    def test_only_explicit_selected_channel_is_tested(self, probe):
        self.settings.channels = ["telegram"]
        self.settings.save(update_fields=["channels", "updated_at"])
        probe.return_value = {
            "ok": True, "message": "Connected to the chosen Telegram channel."
        }
        response = self.client.post(
            reverse("staff_social_autopilot_test_connections")
        )
        self.assertEqual(response.status_code, 302)
        probe.assert_called_once_with("telegram")

    def test_queue_hides_unrelated_posts_and_shows_failed_deliveries(self):
        slot = timezone.now() + timedelta(hours=4)
        manual = ScheduledPost.objects.create(
            title="Marketing team post", caption="Editorial calendar",
            channels=["telegram"], scheduled_for=slot,
            notes="Created manually",
            status=ScheduledPost.STATUS_SCHEDULED,
        )
        automatic = ScheduledPost.objects.create(
            title="Autopilot networking promotion", caption="Network equipment",
            channels=["telegram"], scheduled_for=slot,
            notes="[social-autopilot]:2026101718:1:telegram",
            status=ScheduledPost.STATUS_SCHEDULED,
        )
        plan = PostAutomationPlan.objects.create(
            post=automatic, mode=PostAutomationPlan.MODE_AUTOMATIC,
        )
        failure = PostChannelDelivery.objects.create(
            plan=plan, post=automatic, channel="telegram",
            status=PostChannelDelivery.STATUS_FAILED,
            last_error="Telegram returned a delivery error",
        )
        response = self.client.get(reverse("staff_automation_control"))
        self.assertEqual(response.status_code, 200)
        displayed = list(response.context["upcoming_social_posts"])
        self.assertIn(automatic, displayed)
        self.assertNotIn(manual, displayed)
        failed = response.context["failed_social_posts"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["delivery"], failure)
        self.assertContains(response, "Social deliveries needing review")
        self.assertContains(response, "Telegram returned a delivery error")

    @patch("automation.staff_views.channel_is_configured", return_value=True)
    def test_credentials_are_not_misrepresented_as_live_tested(self, _configured):
        response = self.client.get(reverse("staff_automation_control"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credentials set")
        self.assertContains(response, "Test selected connections")
