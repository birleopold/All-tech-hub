"""Regression coverage for duplicate SKU controls across existing staff editors."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from inventory.forms import ProductCommercialCoreForm, ProductStaffForm
from inventory.views import ProductVariantFormSet


@override_settings(SECURE_SSL_REDIRECT=False)
class ProductIdentityControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Computers", slug="sku-tests-computers")
        cls.category = category
        cls.one = Product.objects.create(
            category=category, name="Workstation", slug="sku-check-workstation",
            price=Decimal("120000"), sku="WS-001", is_published=True,
        )
        cls.two = Product.objects.create(
            category=category, name="Desktop", slug="sku-check-desktop",
            price=Decimal("95000"), sku="DT-002", is_published=True,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.two, name="16GB", sku="OPT-16",
            price=Decimal("110000"), stock_quantity=1,
        )
        cls.staff = get_user_model().objects.create_user(
            username="sku-reviewer", is_staff=True, password="pw",
        )
        cls.customer = get_user_model().objects.create_user(
            username="sku-customer", password="pw",
        )

    def product_data(self, product, sku):
        return {
            "category": str(product.category_id),
            "kind": product.kind, "name": product.name, "sku": sku,
            "short_description": product.short_description,
            "description": product.description, "price": str(product.price),
            "compare_at_price": "", "track_inventory": "on",
            "stock_quantity": str(product.stock_quantity),
            "service_duration_hours": "", "is_published": "on",
            "is_featured": "", "image": "",
        }

    def test_product_form_rejects_case_and_whitespace_collisions(self):
        form = ProductStaffForm(
            data=self.product_data(self.two, "  ws-001  "),
            instance=self.two,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("sku", form.errors)

    def test_product_form_blocks_existing_variant_sku(self):
        form = ProductStaffForm(
            data=self.product_data(self.one, "opt-16"),
            instance=self.one,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("sku", form.errors)

    def test_legacy_sku_is_editable_if_unchanged(self):
        form = ProductStaffForm(
            data=self.product_data(self.one, "WS-001"),
            instance=self.one,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_commercial_editor_uses_same_sku_rule(self):
        form = ProductCommercialCoreForm(
            data=self.product_data(self.two, " WS-001 "),
            instance=self.two,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("sku", form.errors)

    def test_variant_formset_rejects_sku_of_other_product(self):
        # Existing variant edited to collide with another product SKU.
        data = {
            "variants-TOTAL_FORMS": "1",
            "variants-INITIAL_FORMS": "1",
            "variants-MIN_NUM_FORMS": "0",
            "variants-MAX_NUM_FORMS": "1000",
            "variants-0-id": str(self.variant.pk),
            "variants-0-product": str(self.two.pk),
            "variants-0-name": "16GB",
            "variants-0-sku": "ws-001",
            "variants-0-price": "110000.00",
            "variants-0-compare_at_price": "",
            "variants-0-track_inventory": "on",
            "variants-0-stock_quantity": "1",
            "variants-0-sort_order": "0",
            "variants-0-is_active": "on",
        }
        formset = ProductVariantFormSet(data=data, instance=self.two)
        formset.parent_sku = self.two.sku
        self.assertFalse(formset.is_valid())
        self.assertIn("sku", formset.forms[0].errors)

    def test_staff_only_suggestions_are_read_only(self):
        url = reverse("staff_product_identity_check")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.staff)
        response = self.client.get(
            url, {"sku": " ws-001 ", "name": "workstation"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sku_conflict"]["name"], "Workstation")
        self.assertEqual(len(response.json()["name_matches"]), 1)
