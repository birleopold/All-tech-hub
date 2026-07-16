from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from automation.models import AutomationJob, PostAutomationPlan, PostChannelDelivery
from automation.services import recover_stale_jobs
from catalog.models import Category, Product
from marketing.models import ScheduledPost


class StaleAutomationRecoveryTests(TestCase):
    def test_exhausted_stale_job_updates_delivery_and_plan(self):
        category = Category.objects.create(name="Recovery", slug="recovery")
        product = Product.objects.create(
            category=category,
            name="Recovery Product",
            slug="recovery-product",
            price=Decimal("10000.00"),
            stock_quantity=1,
        )
        post = ScheduledPost.objects.create(
            product=product,
            title="Recovery post",
            caption="Recovery test",
            channels=["facebook"],
            status=ScheduledPost.STATUS_READY,
        )
        plan = PostAutomationPlan.objects.create(
            post=post,
            mode=PostAutomationPlan.MODE_AUTOMATIC,
            status=PostAutomationPlan.STATUS_RUNNING,
        )
        delivery = PostChannelDelivery.objects.create(
            plan=plan,
            post=post,
            channel="facebook",
            method=PostChannelDelivery.METHOD_AUTOMATIC,
            status=PostChannelDelivery.STATUS_RUNNING,
        )
        AutomationJob.objects.create(
            idempotency_key="stale:facebook",
            job_type=AutomationJob.TYPE_SOCIAL_POST,
            status=AutomationJob.STATUS_RUNNING,
            delivery=delivery,
            payload={"post_id": post.pk, "channel": "facebook"},
            scheduled_for=timezone.now() - timedelta(hours=1),
            next_attempt_at=timezone.now() - timedelta(hours=1),
            attempt_count=1,
            max_attempts=1,
            locked_at=timezone.now() - timedelta(minutes=30),
            locked_by="dead-worker",
        )

        self.assertEqual(recover_stale_jobs(stale_minutes=15), 1)

        delivery.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(delivery.status, PostChannelDelivery.STATUS_FAILED)
        self.assertEqual(plan.status, PostAutomationPlan.STATUS_FAILED)
