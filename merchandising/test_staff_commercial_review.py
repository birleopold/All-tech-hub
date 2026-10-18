from decimal import Decimal

from django.contrib.auth.models import User, Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from core.models import AuditEvent
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


@override_settings(SECURE_SSL_REDIRECT=False)
class StaffCommercialReviewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Laptops",
            slug="staff-review-laptops",
            description="Laptop computers for work and study.",
        )
        self.product = Product.objects.create(
            category=self.category,
            kind=Product.KIND_PHYSICAL,
            name="Dell Latitude Review Laptop",
            slug="dell-latitude-review-laptop",
            sku="DL-OLD",
            short_description="Existing public description for review.",
            description="Existing detailed product information awaiting staff verification.",
            price=Decimal("1500000"),
            stock_quantity=2,
            is_published=True,
        )
        self.user = User.objects.create_user(
            "commercial-reviewer",
            "reviewer@example.com",
            "pw",
            is_staff=True,
        )
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=[
                "change_product", "change_productgrowthdata",
                "change_productcommerceprofile",
            ]
        ))
        self.url = reverse("staff_product_commercial_review", args=[self.product.pk])

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_open_review_workspace(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Commercial product review")
        self.assertContains(response, "Merchant gaps still blocking approval")
        self.assertContains(response, "Identity, condition and feed metadata")
        self.assertContains(response, "Inspected specifications and delivery")

    def test_review_saves_all_fact_groups_and_keeps_merchant_locked(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {
                "core-name": "Dell Latitude 7420 Core i7 Laptop",
                "core-sku": "DL7420",
                "core-short_description": "Tested Dell business laptop with clear condition and specifications.",
                "core-description": (
                    "A detailed customer-facing description of the exact Dell Latitude "
                    "7420 unit, its inspected condition, included charger and warranty."
                ),
                "core-price": "1850000",
                "core-compare_at_price": "2000000",
                "core-track_inventory": "on",
                "core-stock_quantity": "3",
                "core-is_published": "on",
                "core-is_featured": "on",
                "growth-brand": "Dell",
                "growth-condition": ProductGrowthData.CONDITION_REFURBISHED,
                "growth-gtin": "",
                "growth-mpn": "LAT-7420-I7",
                "growth-google_product_category": "Electronics > Computers > Laptops",
                "growth-custom_label_0": "refurbished-business-laptop",
                "growth-shipping_label": "standard",
                "commerce-processor_family": "Intel Core i7",
                "commerce-processor_generation": "11th Gen",
                "commerce-ram_capacity": "16GB",
                "commerce-ram_type": "DDR4",
                "commerce-storage_capacity": "512GB",
                "commerce-storage_type": "SSD",
                "commerce-screen_size": "14 inches",
                "commerce-screen_resolution": "1920 × 1080",
                "commerce-graphics": "Intel Iris Xe Graphics",
                "commerce-operating_system": "Windows 11 Pro",
                "commerce-battery_health_note": "Battery tested; runtime confirmed during inspection.",
                "commerce-keyboard_condition": "Keyboard tested and fully functional.",
                "commerce-accessories_included": "Compatible charger",
                "commerce-warranty_months": "6",
                "commerce-condition_notes": "Refurbished unit with light signs of normal use.",
                "commerce-actual_photos": "on",
                "commerce-delivery_note": "Delivery or collection confirmed before payment.",
                "commerce-merchant_enabled": "on",
                "commerce-merchant_shipping_price": "15000",
                "commerce-merchant_free_shipping": "",
            },
        )

        self.assertRedirects(response, self.url)
        self.product.refresh_from_db()
        growth = ProductGrowthData.objects.get(product=self.product)
        profile = ProductCommerceProfile.objects.get(product=self.product)

        self.assertEqual(self.product.name, "Dell Latitude 7420 Core i7 Laptop")
        self.assertEqual(self.product.sku, "DL7420")
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertEqual(growth.brand, "Dell")
        self.assertEqual(growth.condition, ProductGrowthData.CONDITION_REFURBISHED)
        self.assertEqual(growth.mpn, "LAT-7420-I7")
        self.assertEqual(profile.processor_family, "Intel Core i7")
        self.assertEqual(profile.ram_capacity, "16GB")
        self.assertEqual(profile.warranty_months, 6)
        self.assertTrue(profile.actual_photos)
        self.assertFalse(profile.merchant_enabled)
        self.assertTrue(
            AuditEvent.objects.filter(
                verb="catalog.commercial_profile_reviewed",
                target_id=self.product.pk,
            ).exists()
        )

    def test_staff_without_catalogue_edit_permissions_cannot_save(self):
        read_only = User.objects.create_user(
            "read-only-commercial", "readonly@example.com", "pw", is_staff=True
        )
        self.client.force_login(read_only)
        response = self.client.post(self.url, {"core-name": "Unauthorized change"})
        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Dell Latitude Review Laptop")
