"""Regression tests: storefront prices must match selectable options."""
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant


@override_settings(SECURE_SSL_REDIRECT=False)
class PurchasableVariantPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Devices", slug="available-price-devices")
        cls.laptop = Product.objects.create(
            category=category, name="Variable Price Laptop", slug="variable-price-laptop",
            price=Decimal("999999"), is_published=True, stock_quantity=0,
        )
        cls.old = ProductVariant.objects.create(
            product=cls.laptop, name="4 GB configuration", price=Decimal("600000"),
            stock_quantity=0, track_inventory=True, is_active=True,
        )
        cls.sellable = ProductVariant.objects.create(
            product=cls.laptop, name="8 GB configuration", price=Decimal("850000"),
            stock_quantity=2, track_inventory=True, is_active=True,
        )
        cls.service = Product.objects.create(
            category=category, name="Network Setup Options",
            slug="network-setup-options", kind=Product.KIND_SERVICE,
            price=Decimal("0"), track_inventory=False, is_published=True,
        )
        cls.estimate = ProductVariant.objects.create(
            product=cls.service, name="Custom installation", price=Decimal("0"),
            track_inventory=False, is_active=True,
        )
        cls.fixed = ProductVariant.objects.create(
            product=cls.service, name="Basic setup", price=Decimal("80000"),
            track_inventory=False, is_active=True,
        )

    def test_available_variant_sets_public_from_price_and_price_filter(self):
        response = self.client.get(
            reverse("product_list"), {"q": "Variable Price Laptop"}
        )
        self.assertEqual(response.status_code, 200)
        card = response.context["products"][0]
        self.assertEqual(card.public_price, Decimal("850000"))
        self.assertEqual(card.public_min_price, Decimal("850000"))
        self.assertNotIn(
            self.laptop.pk,
            [card.pk for card in self.client.get(
                reverse("product_list"),
                {"q": "Variable Price Laptop", "max_price": "700000"}
            ).context["products"]]
        )
        detail = self.client.get(self.laptop.get_absolute_url())
        self.assertEqual(detail.context["product"].public_price, Decimal("850000"))
        self.assertContains(detail, "8 GB configuration")
        self.assertContains(detail, "4 GB configuration")
        self.assertContains(detail, "disabled")

    def test_mixed_quote_and_paid_service_does_not_display_free_from_price(self):
        detail = self.client.get(self.service.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["product"].public_price, Decimal("80000"))
        self.assertContains(detail, "Custom installation")
        self.assertContains(detail, "Quotation required")
        self.assertContains(detail, "Basic setup")
        self.assertContains(detail, "Add priced service to request")
        self.assertNotContains(detail, "From UGX 0")
        schema = json.loads(str(detail.context["product_schema_json"]))
        self.assertEqual(schema["@type"], "Service")
        self.assertEqual(schema["offers"]["price"], "80000")
        self.assertEqual(schema["offers"]["priceCurrency"], "UGX")
        result = self.client.get(reverse("catalog_suggestions"), {"q": "Network Setup Options"}).json()
        price = next(p["price"] for p in result["products"] if p["name"] == self.service.name)
        self.assertEqual(price, "80000")

    def test_unpriced_services_are_not_treated_as_free_in_price_filters(self):
        Product.objects.create(
            category=self.laptop.category, kind=Product.KIND_SERVICE,
            name="Specialist quotation only service",
            slug="specialist-quotation-only-service",
            price=Decimal("0"), is_published=True, track_inventory=False,
        )
        filtered = self.client.get(
            reverse("product_list"),
            {"kind": "service", "min_price": "0", "max_price": "100000"},
        )
        names = [p.name for p in filtered.context["products"]]
        self.assertIn(self.service.name, names)
        self.assertNotIn("Specialist quotation only service", names)

        available = self.client.get(
            reverse("product_list"), {"kind": "service", "available": "1"}
        )
        available_names = [p.name for p in available.context["products"]]
        self.assertIn(self.service.name, available_names)
        self.assertNotIn("Specialist quotation only service", available_names)

        ordered = self.client.get(
            reverse("product_list"), {"kind": "service", "sort": "price_low"}
        )
        self.assertEqual(ordered.context["products"][0].name, self.service.name)
        self.assertEqual(
            ordered.context["products"][-1].name,
            "Specialist quotation only service",
        )

    def test_zero_only_service_search_result_uses_unknown_price(self):
        service = Product.objects.create(
            category=self.laptop.category, kind=Product.KIND_SERVICE,
            name="Cable survey quote required", slug="survey-only-quote",
            price=Decimal("0"), is_published=True, track_inventory=False,
        )
        response = self.client.get(reverse("catalog_suggestions"), {"q": "Cable survey"})
        self.assertEqual(response.status_code, 200)
        entry = next(p for p in response.json()["products"] if p["name"] == service.name)
        self.assertIsNone(entry["price"])
