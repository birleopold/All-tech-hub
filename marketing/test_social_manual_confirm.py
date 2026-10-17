"""Manual publication requires actual operator confirmation and never bypasses automation."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from automation.models import PostAutomationPlan, PostChannelDelivery
from marketing.models import ScheduledPost


class ManualPublishingControlsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(
            username="phase7-post-editor", password="test-password",
            email="phase7-editor@example.com",
        )
        cls.staff = get_user_model().objects.create_user(
            username="phase7-post-other", password="test-password",
            is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.editor)

    def make_post(self, *, channels=None):
        return ScheduledPost.objects.create(
            title="Manually shared laptop", caption="Latest laptops",
            channels=channels or ["telegram"],
            status=ScheduledPost.STATUS_DRAFT,
        )

    def test_manual_post_requires_confirmed_external_publication(self):
        post = self.make_post()
        url = reverse("staff_marketing_post_published", args=[post.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.status, ScheduledPost.STATUS_DRAFT)
        self.assertEqual(
            self.client.post(url, {"confirm_posted": "yes"}).status_code, 302
        )
        post.refresh_from_db()
        self.assertEqual(post.status, ScheduledPost.STATUS_PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertEqual(self.client.post(url, {"confirm_posted": "yes"}).status_code, 302)

    def test_manual_plan_updates_delivery_without_worker_job(self):
        post = self.make_post()
        plan = PostAutomationPlan.objects.create(
            post=post, mode=PostAutomationPlan.MODE_MANUAL,
        )
        self.client.post(
            reverse("staff_marketing_post_published", args=[post.pk]),
            {"confirm_posted": "yes"},
        )
        plan.refresh_from_db()
        self.assertEqual(plan.status, PostAutomationPlan.STATUS_PUBLISHED)
        delivery = PostChannelDelivery.objects.get(post=post)
        self.assertEqual(delivery.status, PostChannelDelivery.STATUS_PUBLISHED)
        self.assertEqual(delivery.method, PostChannelDelivery.METHOD_MANUAL)

    def test_cannot_mark_multi_channel_or_auto_post_as_fully_published(self):
        both = self.make_post(channels=["telegram", "facebook"])
        automatic = self.make_post()
        PostAutomationPlan.objects.create(
            post=automatic, mode=PostAutomationPlan.MODE_AUTOMATIC,
        )
        for post in (both, automatic):
            response = self.client.post(
                reverse("staff_marketing_post_published", args=[post.pk]),
                {"confirm_posted": "yes"},
            )
            self.assertEqual(response.status_code, 302)
            post.refresh_from_db()
            self.assertEqual(post.status, ScheduledPost.STATUS_DRAFT)

    def test_editor_permission_required(self):
        post = self.make_post()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("staff_marketing_post_published", args=[post.pk]),
            {"confirm_posted": "yes"},
        )
        self.assertEqual(response.status_code, 404)
        post.refresh_from_db()
        self.assertEqual(post.status, ScheduledPost.STATUS_DRAFT)
