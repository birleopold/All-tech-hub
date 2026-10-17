from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from marketing.models import (
    CampaignLink,
    MarketingCampaign,
    MarketingLead,
    ScheduledPost,
)


class MarketingAutomationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="marketer", password="safe-password", is_staff=True
        )
        self.category = Category.objects.create(
            name="Marketing Products", slug="marketing-products"
        )
        self.product = Product.objects.create(
            category=self.category,
            name="LEOSOFT Test Laptop",
            slug="leosoft-test-laptop",
            sku="MKT-001",
            price=Decimal("2500000"),
            stock_quantity=3,
            is_published=True,
        )
        self.campaign = MarketingCampaign.objects.create(
            name="Back to School", status=MarketingCampaign.STATUS_ACTIVE
        )
        self.link = CampaignLink.objects.create(
            name="WhatsApp laptop campaign",
            campaign=self.campaign,
            product=self.product,
            destination_url="https://leosoftug.com/catalog/leosoft-test-laptop/",
            source="whatsapp",
            medium="social",
            content=self.product.slug,
        )

    def test_staff_dashboard_requires_login(self):
        response = self.client.get(reverse("staff_marketing_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_marketing_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketing automation")

    def test_tracking_link_records_click_and_attribution(self):
        response = self.client.get(
            reverse("marketing_track", kwargs={"code": self.link.code})
        )
        self.assertEqual(response.status_code, 302)
        self.link.refresh_from_db()
        self.assertEqual(self.link.click_count, 1)
        attribution = self.client.session["marketing_attribution"]
        self.assertEqual(attribution["source"], "whatsapp")
        self.assertEqual(attribution["link_id"], self.link.pk)

    def test_contact_submission_becomes_attributed_lead(self):
        self.client.get(
            reverse("marketing_track", kwargs={"code": self.link.code})
        )
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Test Customer",
                "email": "customer@example.com",
                "phone": "0700000000",
                "subject": "Laptop enquiry",
                "message": "Please send me the available options.",
            },
        )
        self.assertEqual(response.status_code, 302)
        lead = MarketingLead.objects.get(email="customer@example.com")
        self.assertEqual(lead.campaign, self.campaign)
        self.assertEqual(lead.product, self.product)
        self.assertEqual(lead.source, "whatsapp")
        self.link.refresh_from_db()
        self.assertEqual(self.link.lead_count, 1)

    def test_product_feeds_include_published_product(self):
        # Feeds must reject imageless products; use a real product photo to
        # test a legitimately exportable listing.
        image_bytes = BytesIO()
        Image.new("RGB", (240, 240), "white").save(image_bytes, format="JPEG")
        self.product.image.save(
            "marketing-feed-test.jpg",
            SimpleUploadedFile("marketing-feed-test.jpg", image_bytes.getvalue(),
                               content_type="image/jpeg"),
            save=True,
        )
        csv_response = self.client.get(reverse("marketing_product_feed_csv"))
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(b"LEOSOFT Test Laptop", csv_response.content)

        json_response = self.client.get(reverse("marketing_product_feed_json"))
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["products"][0]["title"], self.product.name)

        xml_response = self.client.get(reverse("marketing_product_feed_xml"))
        self.assertEqual(xml_response.status_code, 200)
        self.assertIn(b"LEOSOFT Test Laptop", xml_response.content)

    def test_qr_download_is_staff_only(self):
        url = reverse("staff_marketing_link_qr", args=[self.link.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")

    def test_due_posts_are_moved_to_ready_queue(self):
        post = ScheduledPost.objects.create(
            title="Due post",
            caption="A ready caption",
            channels=["facebook", "whatsapp"],
            status=ScheduledPost.STATUS_SCHEDULED,
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        output = StringIO()
        call_command("prepare_due_marketing_posts", stdout=output)
        post.refresh_from_db()
        self.assertEqual(post.status, ScheduledPost.STATUS_READY)
        self.assertIn("Prepared 1", output.getvalue())
