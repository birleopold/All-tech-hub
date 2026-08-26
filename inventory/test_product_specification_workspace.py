from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


class ProductSpecificationWorkspaceTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="catalog-editor",
            password="test-password-2026",
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.category = Category.objects.create(name="Laptops", slug="laptops")

    def test_new_product_page_shows_condition_and_specification_fields(self):
        response = self.client.get(reverse("staff_product_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="growth-condition"')
        self.assertContains(response, 'name="commerce-processor_family"')
        self.assertContains(response, 'name="commerce-ram_capacity"')
        self.assertContains(response, 'name="commerce-storage_capacity"')
        self.assertContains(response, 'name="commerce-warranty_months"')

    def test_create_saves_core_condition_and_specs_together(self):
        response = self.client.post(
            reverse("staff_product_create"),
            {
                "category": self.category.pk,
                "kind": Product.KIND_PHYSICAL,
                "name": "ThinkPad T14",
                "sku": "T14-001",
                "short_description": "Business laptop",
                "description": "A tested business laptop.",
                "price": "1800000.00",
                "compare_at_price": "",
                "track_inventory": "on",
                "stock_quantity": "1",
                "service_duration_hours": "",
                "is_published": "on",
                "image": "",
                "growth-brand": "Lenovo",
                "growth-condition": ProductGrowthData.CONDITION_REFURBISHED,
                "growth-gtin": "",
                "growth-mpn": "20S0",
                "growth-google_product_category": "Electronics > Computers > Laptops",
                "growth-custom_label_0": "",
                "growth-shipping_label": "",
                "commerce-processor_family": "Intel Core i7",
                "commerce-processor_generation": "10th Gen",
                "commerce-ram_capacity": "16 GB",
                "commerce-ram_type": "DDR4",
                "commerce-storage_capacity": "512 GB",
                "commerce-storage_type": "NVMe SSD",
                "commerce-screen_size": "14 inches",
                "commerce-screen_resolution": "1920 x 1080",
                "commerce-graphics": "Intel UHD",
                "commerce-operating_system": "Windows 11 Pro",
                "commerce-battery_health_note": "Good",
                "commerce-keyboard_condition": "Excellent",
                "commerce-accessories_included": "Original charger",
                "commerce-warranty_months": "3",
                "commerce-condition_notes": "Professionally refurbished and tested.",
                "commerce-delivery_note": "Delivery available in Kampala",
                "commerce-merchant_shipping_price": "",
            },
        )
        product = Product.objects.get(name="ThinkPad T14")
        self.assertRedirects(
            response, reverse("staff_product_edit", kwargs={"pk": product.pk})
        )
        self.assertEqual(product.growth_data.condition, "refurbished")
        self.assertEqual(product.growth_data.brand, "Lenovo")
        self.assertEqual(product.commerce_profile.processor_family, "Intel Core i7")
        self.assertEqual(product.commerce_profile.ram_capacity, "16 GB")
        self.assertEqual(product.commerce_profile.storage_capacity, "512 GB")
        self.assertEqual(product.commerce_profile.warranty_months, 3)

    def test_edit_page_handles_products_without_existing_related_records(self):
        product = Product.objects.create(
            category=self.category,
            kind=Product.KIND_PHYSICAL,
            name="Legacy product",
            slug="legacy-product",
            price="100.00",
        )
        response = self.client.get(
            reverse("staff_product_edit", kwargs={"pk": product.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="growth-condition"')
        self.assertContains(response, 'name="commerce-processor_family"')
