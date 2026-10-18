"""Merchant feed readiness is internal, never public product-page content."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


@override_settings(SECURE_SSL_REDIRECT=False)
class MerchantReadinessVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(
            name="Readiness test laptops", slug="readiness-visibility-laptops"
        )
        cls.product = Product.objects.create(
            category=category,
            name="Readiness visibility test laptop",
            slug="readiness-visibility-test-laptop",
            price=1250000,
            stock_quantity=2,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.product,
            brand="Lenovo",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
        )
        cls.profile = ProductCommerceProfile.objects.create(
            product=cls.product,
            processor_family="Intel Core i5",
            ram_capacity="8GB",
        )
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username="readiness-customer", password="test-only"
        )
        cls.staff = User.objects.create_superuser(
            username="readiness-manager",
            email="readiness-manager@example.com",
            password="test-only",
        )

    def _assert_public_page_has_no_internal_readiness(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, "Intel Core i5")
        self.assertContains(response, "8GB")
        for forbidden in (
            "Staff Merchant readiness",
            "strict Merchant readiness",
            "merchant approval",
            "identity verification",
            "stock verification date",
            "shipping price or free-shipping confirmation",
            "Merchant gaps still blocking approval",
        ):
            self.assertNotContains(response, forbidden)
        self.assertNotIn("merchant_missing_fields", response.context)

    def test_merchant_readiness_is_not_shown_to_anonymous_customer(self):
        self._assert_public_page_has_no_internal_readiness()

    def test_merchant_readiness_is_not_shown_to_signed_in_customer(self):
        self.client.force_login(self.customer)
        self._assert_public_page_has_no_internal_readiness()

    def test_merchant_readiness_is_not_shown_on_public_page_to_staff(self):
        self.client.force_login(self.staff)
        self._assert_public_page_has_no_internal_readiness()

    def test_staff_commercial_review_keeps_score_and_actionable_missing_fields(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("staff_product_commercial_review", args=[self.product.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merchant readiness")
        self.assertContains(response, "Merchant gaps still blocking approval")
        self.assertContains(response, "merchant approval")
        self.assertContains(response, "identity verification")
        self.assertEqual(
            response.context["merchant_readiness_score"],
            self.profile.merchant_readiness_score,
        )

    def test_unverified_staff_tasks_do_not_leak_to_product_detail(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product details")
        for task in (
            "Inspected product information",
            "Confirm actual photos", "Confirm warranty", "Confirm charger",
            "Delivery or collection confirmed before payment",
        ):
            self.assertNotContains(response, task)

    def test_customer_can_see_only_recorded_product_assurances(self):
        profile = ProductCommerceProfile.objects.get(product=self.product)
        profile.actual_photos = True
        profile.warranty_months = 6
        profile.charger_included = False
        profile.delivery_note = "Collection by arrangement"
        profile.save()
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "Actual product photos")
        self.assertContains(response, "6-month warranty")
        self.assertContains(response, "Charger not included")
        self.assertContains(response, "Collection by arrangement")
        self.assertNotContains(response, "Confirm charger")
