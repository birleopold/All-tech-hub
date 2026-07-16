from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from automation.models import AutomationJob, PostAutomationPlan, PostChannelDelivery
from catalog.models import Category, Product
from marketing.models import ScheduledPost


class AutomationCancellationTests(TestCase):
    def test_failed_social_job_can_be_closed_as_manual(self):
        category = Category.objects.create(name="Accessories", slug="accessories")
        product = Product.objects.create(
            category=category,
            name="USB Hub",
            slug="usb-hub",
            price=Decimal("50000.00"),
            stock_quantity=3,
        )
        post = ScheduledPost.objects.create(
            product=product,
            title="USB Hub post",
            caption="USB hubs from LEOSOFT UG LTD.",
            channels=["facebook"],
            status=ScheduledPost.STATUS_READY,
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        plan = PostAutomationPlan.objects.create(
            post=post,
            mode=PostAutomationPlan.MODE_AUTOMATIC,
            status=PostAutomationPlan.STATUS_FAILED,
        )
        delivery = PostChannelDelivery.objects.create(
            plan=plan,
            post=post,
            channel="facebook",
            method=PostChannelDelivery.METHOD_AUTOMATIC,
            status=PostChannelDelivery.STATUS_FAILED,
            last_error="Permission denied",
        )
        job = AutomationJob.objects.create(
            idempotency_key="social:test:facebook",
            job_type=AutomationJob.TYPE_SOCIAL_POST,
            status=AutomationJob.STATUS_FAILED,
            delivery=delivery,
            payload={"post_id": post.pk, "channel": "facebook"},
            scheduled_for=timezone.now(),
            next_attempt_at=timezone.now(),
            completed_at=timezone.now(),
            last_error="Permission denied",
        )

        call_command(
            "cancel_automation_job",
            job.idempotency_key,
            reason="Publish this post manually instead.",
        )

        job.refresh_from_db()
        delivery.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_CANCELLED)
        self.assertEqual(delivery.status, PostChannelDelivery.STATUS_MANUAL)
        self.assertEqual(plan.status, PostAutomationPlan.STATUS_MANUAL)
