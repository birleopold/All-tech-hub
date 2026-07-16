from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from automation.connectors import ConnectorError
from automation.models import AutomationJob, PostAutomationPlan, PostChannelDelivery
from automation.services import (
    configure_post_plan,
    process_automation_jobs,
    queue_due_growth_jobs,
    queue_due_posts,
)
from catalog.models import Category, Product
from growth.models import GrowthSettings, SavedCart
from marketing.models import ScheduledPost


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sales@leosoftug.com",
    META_AUTO_PUBLISH_ENABLED=True,
    META_PAGE_ID="page-123",
    META_PAGE_ACCESS_TOKEN="test-token-never-sent",
    AUTOMATION_JOB_MAX_ATTEMPTS=3,
)
class DurableAutomationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Routers", slug="routers")
        self.product = Product.objects.create(
            category=self.category,
            name="Alcatel 4G Router",
            slug="alcatel-4g-router",
            price=Decimal("250000.00"),
            stock_quantity=5,
            is_published=True,
        )

    def make_post(self, *, channels, mode):
        post = ScheduledPost.objects.create(
            product=self.product,
            title="Alcatel campaign",
            caption="Fast 4G internet from LEOSOFT UG LTD.",
            channels=channels,
            status=ScheduledPost.STATUS_SCHEDULED,
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        configure_post_plan(post, mode=mode)
        return post

    def test_manual_post_becomes_ready_without_fake_publication(self):
        post = self.make_post(
            channels=["facebook", "whatsapp"],
            mode=PostAutomationPlan.MODE_MANUAL,
        )

        result = queue_due_posts()

        post.refresh_from_db()
        plan = post.automation_plan
        self.assertEqual(result["queued"], 0)
        self.assertEqual(result["manual"], 2)
        self.assertEqual(post.status, ScheduledPost.STATUS_READY)
        self.assertEqual(plan.status, PostAutomationPlan.STATUS_MANUAL)
        self.assertEqual(AutomationJob.objects.count(), 0)
        self.assertEqual(
            set(plan.deliveries.values_list("status", flat=True)),
            {PostChannelDelivery.STATUS_MANUAL},
        )

    @patch("automation.services.publish_social_post")
    def test_facebook_job_publishes_and_records_external_result(self, mocked_publish):
        mocked_publish.return_value = {
            "external_id": "page-123_456",
            "external_url": "https://www.facebook.com/example/posts/456",
        }
        post = self.make_post(
            channels=["facebook"],
            mode=PostAutomationPlan.MODE_AUTOMATIC,
        )

        queued = queue_due_posts()
        processed = process_automation_jobs()

        post.refresh_from_db()
        plan = post.automation_plan
        delivery = plan.deliveries.get(channel="facebook")
        job = delivery.job
        self.assertEqual(queued["queued"], 1)
        self.assertEqual(processed["succeeded"], 1)
        self.assertEqual(job.status, AutomationJob.STATUS_SUCCEEDED)
        self.assertEqual(delivery.status, PostChannelDelivery.STATUS_PUBLISHED)
        self.assertEqual(delivery.external_id, "page-123_456")
        self.assertEqual(plan.status, PostAutomationPlan.STATUS_PUBLISHED)
        self.assertEqual(post.status, ScheduledPost.STATUS_PUBLISHED)
        mocked_publish.assert_called_once()

    @patch("automation.services.publish_social_post")
    def test_transient_social_error_is_retried_without_marking_published(
        self, mocked_publish
    ):
        mocked_publish.side_effect = ConnectorError(
            "Temporary Meta outage.",
            retryable=True,
        )
        post = self.make_post(
            channels=["facebook"],
            mode=PostAutomationPlan.MODE_AUTOMATIC,
        )
        queue_due_posts()

        result = process_automation_jobs()

        job = AutomationJob.objects.get()
        delivery = PostChannelDelivery.objects.get()
        post.refresh_from_db()
        self.assertEqual(result["retried"], 1)
        self.assertEqual(job.status, AutomationJob.STATUS_RETRY)
        self.assertEqual(delivery.status, PostChannelDelivery.STATUS_RETRYING)
        self.assertEqual(post.status, ScheduledPost.STATUS_READY)
        self.assertIsNone(post.published_at)

    def test_due_saved_cart_email_is_queued_and_sent_once(self):
        growth = GrowthSettings.load()
        growth.abandoned_cart_enabled = True
        growth.abandoned_cart_first_delay_hours = 1
        growth.save()
        saved = SavedCart.objects.create(
            session_key="automation-cart-session",
            customer_name="Test Buyer",
            email="buyer@example.com",
            cart_data={f"p:{self.product.pk}": 1},
            subtotal=self.product.price,
            last_activity=timezone.now() - timedelta(hours=2),
        )

        queued = queue_due_growth_jobs()
        processed = process_automation_jobs()

        saved.refresh_from_db()
        self.assertEqual(queued["queued_cart"], 1)
        self.assertEqual(processed["succeeded"], 1)
        self.assertIsNotNone(saved.first_reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)

        queue_due_growth_jobs()
        process_automation_jobs()
        self.assertEqual(len(mail.outbox), 1)
