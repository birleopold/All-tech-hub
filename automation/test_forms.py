from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from automation.models import PostAutomationPlan
from catalog.models import Category, Product
from marketing.forms import ScheduledPostForm
from marketing.models import ScheduledPost


class ScheduledPostAutomationFormTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Networking", slug="networking")
        self.product = Product.objects.create(
            category=category,
            name="Router without image",
            slug="router-without-image",
            price=Decimal("100000.00"),
            stock_quantity=2,
        )

    def form_data(self, **overrides):
        data = {
            "title": "Scheduled router post",
            "product": str(self.product.pk),
            "caption": "Reliable routers from LEOSOFT UG LTD.",
            "channels": ["facebook"],
            "publish_mode": PostAutomationPlan.MODE_AUTOMATIC,
            "media_url": "",
            "status": ScheduledPost.STATUS_SCHEDULED,
            "scheduled_for": (
                timezone.localtime(timezone.now() + timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_saving_form_creates_automatic_plan(self):
        form = ScheduledPostForm(data=self.form_data())
        self.assertTrue(form.is_valid(), form.errors)

        post = form.save()

        self.assertEqual(post.automation_plan.mode, PostAutomationPlan.MODE_AUTOMATIC)
        self.assertEqual(post.automation_plan.status, PostAutomationPlan.STATUS_SCHEDULED)

    def test_instagram_automatic_mode_requires_image(self):
        form = ScheduledPostForm(
            data=self.form_data(channels=["instagram"]),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("media_url", form.errors)

    def test_instagram_accepts_public_https_media_url(self):
        form = ScheduledPostForm(
            data=self.form_data(
                channels=["instagram"],
                media_url="https://leosoftug.com/media/products/router.jpg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
