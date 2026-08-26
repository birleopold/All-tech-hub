from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from automation.autopilot import (
    autopilot_readiness,
    cancel_autopilot_post,
    generate_autopilot_calendar,
    queue_product_promotion,
    rebuild_autopilot_calendar,
    reconcile_autopilot_state,
)
from automation.connectors import diagnose_channel, publish_telegram
from automation.models import PostAutomationPlan, SocialAutopilotSettings
from catalog.models import Category, Product
from marketing.models import CampaignLink, ScheduledPost


def image_upload(name="product.jpg"):
    output = BytesIO()
    Image.new("RGB", (80, 80), "blue").save(output, format="JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


class SocialAutopilotTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Networking", slug="networking")
        self.product = Product.objects.create(
            category=category,
            name="5G Router",
            slug="5g-router",
            price=Decimal("450000"),
            short_description="Fast business and home connectivity.",
            stock_quantity=3,
            image=image_upload(),
            is_published=True,
            is_featured=True,
        )
        self.settings = SocialAutopilotSettings.load()
        self.settings.enabled = True
        self.settings.mode = SocialAutopilotSettings.MODE_FULL
        self.settings.channels = ["facebook", "instagram", "telegram"]
        self.settings.posts_per_day = 1
        self.settings.posting_hours = [9]
        self.settings.queue_days = 1
        self.settings.preferred_product = self.product
        self.settings.save()

    def test_full_autopilot_generates_channel_posts_and_consumes_priority(self):
        now = timezone.make_aware(datetime(2026, 8, 26, 8, 0))
        result = generate_autopilot_calendar(now=now)

        self.assertEqual(result["created"], 3)
        self.assertEqual(ScheduledPost.objects.count(), 3)
        self.assertEqual(CampaignLink.objects.count(), 3)
        self.assertEqual(
            ScheduledPost.objects.filter(
                status=ScheduledPost.STATUS_SCHEDULED
            ).count(),
            3,
        )
        self.assertEqual(
            PostAutomationPlan.objects.filter(
                mode=PostAutomationPlan.MODE_AUTOMATIC
            ).count(),
            3,
        )
        self.settings.refresh_from_db()
        self.assertIsNone(self.settings.preferred_product)
        self.assertEqual(generate_autopilot_calendar(now=now)["created"], 0)

    def test_controlled_mode_creates_review_draft(self):
        self.settings.mode = SocialAutopilotSettings.MODE_CONTROLLED
        self.settings.channels = ["facebook"]
        self.settings.save()
        now = timezone.make_aware(datetime(2026, 8, 26, 8, 0))

        result = generate_autopilot_calendar(now=now)

        self.assertEqual(result["created"], 1)
        post = ScheduledPost.objects.get()
        self.assertEqual(post.status, ScheduledPost.STATUS_DRAFT)
        self.assertEqual(post.automation_plan.mode, PostAutomationPlan.MODE_MANUAL)

    def test_stopping_autopilot_cancels_future_posts(self):
        now = timezone.make_aware(datetime(2026, 8, 26, 8, 0))
        generate_autopilot_calendar(now=now)
        self.settings.refresh_from_db()
        self.settings.enabled = False
        self.settings.save(update_fields=["enabled", "updated_at"])

        result = reconcile_autopilot_state(self.settings, now=now)

        self.assertEqual(result["changed"], 3)
        self.assertEqual(
            ScheduledPost.objects.filter(
                status=ScheduledPost.STATUS_CANCELLED
            ).count(),
            3,
        )

    def test_priority_product_creates_review_drafts_when_not_in_full_mode(self):
        self.settings.enabled = False
        self.settings.channels = ["facebook", "telegram"]
        self.settings.save()

        result = queue_product_promotion(self.product)

        self.assertEqual(result["created"], 2)
        self.assertFalse(result["automatic"])
        self.assertEqual(
            ScheduledPost.objects.filter(status=ScheduledPost.STATUS_DRAFT).count(),
            2,
        )
        self.assertTrue(
            all("priority-organic-social" == link.medium for link in CampaignLink.objects.all())
        )

    def test_calendar_rebuild_replaces_future_autopilot_posts(self):
        now = timezone.make_aware(datetime(2026, 8, 26, 8, 0))
        generate_autopilot_calendar(now=now)

        result = rebuild_autopilot_calendar(now=now)

        self.assertEqual(result["cancelled"], 3)
        self.assertEqual(result["created"], 3)
        self.assertEqual(
            ScheduledPost.objects.filter(
                status=ScheduledPost.STATUS_CANCELLED
            ).count(),
            3,
        )
        self.assertEqual(
            ScheduledPost.objects.filter(
                status=ScheduledPost.STATUS_SCHEDULED
            ).count(),
            3,
        )


    def test_readiness_reports_catalogue_and_connection_gaps(self):
        readiness = autopilot_readiness(
            self.settings,
            now=timezone.make_aware(datetime(2026, 8, 26, 8, 0)),
        )

        self.assertEqual(readiness["eligible_products"], 1)
        self.assertEqual(readiness["expected_posts"], 3)
        self.assertEqual(readiness["queued_posts"], 0)
        self.assertFalse(readiness["ready"])
        self.assertTrue(any("credentials" in issue for issue in readiness["issues"]))

    def test_one_autopilot_post_can_be_removed_without_rebuilding_calendar(self):
        now = timezone.make_aware(datetime(2026, 8, 26, 8, 0))
        generate_autopilot_calendar(now=now)
        post = ScheduledPost.objects.order_by("pk").first()

        result = cancel_autopilot_post(post)

        self.assertTrue(result["cancelled"])
        post.refresh_from_db()
        self.assertEqual(post.status, ScheduledPost.STATUS_CANCELLED)
        self.assertEqual(
            post.automation_plan.status,
            PostAutomationPlan.STATUS_CANCELLED,
        )
        self.assertEqual(
            ScheduledPost.objects.exclude(status=ScheduledPost.STATUS_CANCELLED).count(),
            2,
        )


@override_settings(
    TELEGRAM_AUTO_PUBLISH_ENABLED=True,
    TELEGRAM_BOT_TOKEN="secret-token",
    TELEGRAM_CHANNEL_ID="@leosoft",
)
class TelegramConnectorTests(TestCase):
    @patch("automation.connectors.urlopen")
    def test_photo_post_returns_public_channel_url(self, mocked_urlopen):
        response = Mock()
        response.read.return_value = (
            b'{"ok": true, "result": {"message_id": 42, '
            b'"chat": {"username": "leosoft"}}}'
        )
        mocked_urlopen.return_value.__enter__.return_value = response
        post = Mock(caption="A verified product caption")

        result = publish_telegram(
            post=post,
            image_url="https://leosoftug.com/media/product.jpg",
        )

        self.assertEqual(result["external_id"], "42")
        self.assertEqual(result["external_url"], "https://t.me/leosoft/42")


@override_settings(
    TELEGRAM_AUTO_PUBLISH_ENABLED=True,
    TELEGRAM_BOT_TOKEN="secret-token",
    TELEGRAM_CHANNEL_ID="@leosoft",
)
class SocialConnectionDiagnosticTests(TestCase):
    @patch("automation.connectors.urlopen")
    def test_telegram_connection_diagnostic_identifies_channel(self, mocked_urlopen):
        response = Mock()
        response.read.return_value = (
            b'{"ok": true, "result": {"id": -1001, "title": "LEOSOFT Uganda"}}'
        )
        mocked_urlopen.return_value.__enter__.return_value = response

        result = diagnose_channel("telegram")

        self.assertTrue(result["ok"])
        self.assertIn("LEOSOFT Uganda", result["message"])
