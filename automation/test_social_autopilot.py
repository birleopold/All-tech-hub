from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from automation.autopilot import generate_autopilot_calendar
from automation.connectors import publish_telegram
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
