"""Homepage marketing must remain truthful, staff-editable and mobile friendly."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from merchandising.models import HomepagePromotion, ProductCommerceProfile


@override_settings(SECURE_SSL_REDIRECT=False)
class HomepageCampaignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.computers = Category.objects.create(
            name="Laptops", slug="home-campaign-laptops"
        )
        cls.networking = Category.objects.create(
            name="Networking", slug="home-campaign-networking"
        )
        cls.unchecked = Product.objects.create(
            category=cls.computers,
            name="Unchecked featured notebook",
            slug="home-uncertain-featured",
            is_published=True,
            is_featured=True,
            price=1200000,
            stock_quantity=2,
        )
        cls.checked = Product.objects.create(
            category=cls.networking,
            name="Confirmed office router",
            slug="home-checked-router",
            is_published=True,
            price=600000,
            stock_quantity=4,
        )
        ProductCommerceProfile.objects.create(
            product=cls.checked, stock_confirmed_at=timezone.now(),
            processor_family="Dual-core processor",
            ram_capacity="8GB", storage_capacity="256GB",
            storage_type="SSD", warranty_months=6,
        )
        cls.unpublished = Product.objects.create(
            category=cls.computers,
            name="Unpublished workstation",
            slug="home-private-workstation",
            is_published=False,
            price=2000000,
        )
        User = get_user_model()
        cls.manager = User.objects.create_superuser(
            username="home-campaign-manager",
            email="campaign-manager@example.com",
            password="test-password",
        )
        cls.staff = User.objects.create_user(
            username="home-campaign-marketer",
            password="test-password", is_staff=True,
        )
        cls.staff.user_permissions.add(
            Permission.objects.get(codename="change_scheduledpost")
        )
        cls.unrelated = User.objects.create_user(
            username="home-campaign-unrelated", password="test-password",
            is_staff=True,
        )

    def test_homepage_features_recently_verified_stock_first(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["featured_products"][0].pk, self.checked.pk)
        self.assertContains(response, "Confirmed office router")
        self.assertContains(response, "Shop our products")
        self.assertContains(response, 'id="market-hero-search-input"')
        self.assertContains(response, "Find your next upgrade")
        self.assertContains(response, "Shop with confidence")
        self.assertContains(response, "storefront_campaigns.css")
        self.assertContains(response, "storefront_product_cards.css")
        self.assertContains(response, 'data-promotion-slot="hero"')
        self.assertContains(response, 'data-promotion-slot="side_top"')
        self.assertContains(response, 'data-promotion-slot="side_bottom"')
        self.assertContains(response, 'data-storefront-category="home-campaign-networking"')
        self.assertNotContains(response, "In stock — guaranteed")

    def test_product_card_and_details_surface_short_recorded_specifications(self):
        homepage = self.client.get(reverse("home"))
        self.assertContains(homepage, "storefront-card-specs")
        self.assertContains(homepage, "8GB / 256GB SSD")
        detail = self.client.get(self.checked.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "storefront-detail-highlights")
        self.assertContains(detail, "6-month warranty")

    def test_campaign_measurement_respects_existing_analytics_consent(self):
        from pathlib import Path
        source = Path("static/js/marketing_analytics.js").read_text(encoding="utf-8")
        self.assertIn('name: "select_promotion"', source)
        self.assertIn('name: "select_content"', source)
        self.assertIn('promotion && integrationsLoaded', source)
        self.assertNotIn('window.localStorage.setItem("storefront', source)

    def test_active_scheduled_campaign_is_displayed_and_older_one_excluded(self):
        now = timezone.now()
        HomepagePromotion.objects.create(
            slot=HomepagePromotion.HERO,
            headline="Work smarter this season",
            button_label="Explore laptops",
            eyebrow="Office picks",
            supporting_text="Business-ready devices.",
            link_path="/catalog/",
            is_active=True,
            priority=20,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
        )
        HomepagePromotion.objects.create(
            slot=HomepagePromotion.HERO,
            headline="Expired promise",
            button_label="Shop",
            is_active=True,
            end_at=now - timedelta(hours=1),
            priority=100,
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Work smarter this season")
        self.assertContains(response, "Explore laptops")
        self.assertNotContains(response, "Expired promise")

    def test_unpublished_product_cannot_leak_via_campaign(self):
        promotion = HomepagePromotion.objects.create(
            slot=HomepagePromotion.SIDE_TOP,
            headline="Not for public",
            product=self.unpublished, is_active=True,
        )
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Not for public")
        self.assertFalse(promotion.is_live)

    def test_model_rejects_outbound_campaign_paths_and_inverted_dates(self):
        campaign = HomepagePromotion(
            slot="hero", headline="Test", button_label="Explore",
            link_path="https://unrelated.example/",
        )
        with self.assertRaises(ValidationError):
            campaign.full_clean()
        campaign.link_path = "//untrusted.example"
        with self.assertRaises(ValidationError):
            campaign.full_clean()
        campaign.link_path = "/catalog/"
        campaign.start_at = timezone.now()
        campaign.end_at = campaign.start_at - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            campaign.full_clean()

    def test_staff_editor_is_reachable_and_saves_with_audit(self):
        self.client.force_login(self.staff)
        url = reverse("staff_homepage_promotions")
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            "slot": "side_bottom",
            "eyebrow": "Help desk",
            "headline": "Talk to our technicians",
            "supporting_text": "IT support when needed.",
            "button_label": "Explore services",
            "link_path": "/catalog/services/",
            "product": "",
            "priority": "2",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        saved = HomepagePromotion.objects.get(headline="Talk to our technicians")
        self.assertTrue(saved.is_active)
        self.assertContains(self.client.get(reverse("home")), saved.headline)
        from core.models import AuditEvent
        self.assertTrue(
            AuditEvent.objects.filter(verb="storefront.promotion_saved", target_id=saved.pk).exists()
        )
        edit_url = reverse("staff_homepage_promotion_edit", args=[saved.pk])
        self.assertContains(self.client.get(edit_url), saved.headline)

    def test_non_marketing_staff_cannot_see_or_post_campaigns(self):
        url = reverse("staff_homepage_promotions")
        self.client.force_login(self.unrelated)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"headline": "Unauthorised"}).status_code, 403)

    def test_untrusted_image_or_external_path_cannot_be_published(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff_homepage_promotions"), {
            "slot": "hero", "headline": "Fake offer", "button_label": "Buy",
            "link_path": "//bad.example/path", "priority": 1, "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HomepagePromotion.objects.filter(headline="Fake offer").exists())

    def test_campaign_editor_can_preview_unsaved_images_before_publishing(self):
        from pathlib import Path

        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff_homepage_promotions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-campaign-preview-image")
        self.assertContains(response, "preview here before you save")
        self.assertContains(response, "staff_homepage_campaigns.js")
        source = Path("static/js/staff_homepage_campaigns.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("URL.createObjectURL(file)", source)
        self.assertIn("URL.revokeObjectURL(pendingObjectURL)", source)
        self.assertIn('file.type.startsWith("image/")', source)
        self.assertIn('media.replaceChildren(img)', source)

    def test_editor_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        self.assertEqual(
            client.post(reverse("staff_homepage_promotions"), {
                "slot": "hero", "headline": "Bad CSRF"
            }).status_code,
            403,
        )
