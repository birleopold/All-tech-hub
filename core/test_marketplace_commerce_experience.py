from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


class MarketplaceCommerceExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.laptops = Category.objects.create(
            name="Laptops",
            slug="laptops",
            description="Portable computers for work and learning.",
        )
        cls.accessories = Category.objects.create(
            name="Accessories",
            slug="accessories",
            description="Computer accessories and essentials.",
            sort_order=2,
        )
        cls.hp = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="HP ProBook Business Laptop",
            slug="hp-probook-business-laptop",
            sku="HP-PROBOOK-TEST",
            short_description="Core i5 business laptop with 8GB RAM and SSD storage.",
            description="A professional office computer suitable for business and student work.",
            price=Decimal("1200000"),
            compare_at_price=Decimal("1500000"),
            stock_quantity=3,
            reorder_level=1,
            is_published=True,
            is_featured=True,
        )
        ProductGrowthData.objects.create(
            product=cls.hp,
            brand="HP",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
        )
        ProductCommerceProfile.objects.create(
            product=cls.hp,
            identity_verified_at=timezone.now(),
            condition_verified_at=timezone.now(),
        )
        cls.dell = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="Dell Latitude Office Laptop",
            slug="dell-latitude-office-laptop",
            sku="DELL-LATITUDE-TEST",
            short_description="A dependable new business laptop.",
            price=Decimal("2600000"),
            stock_quantity=2,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.dell,
            brand="Dell",
            condition=ProductGrowthData.CONDITION_NEW,
        )
        cls.service = Product.objects.create(
            category=cls.accessories,
            kind=Product.KIND_SERVICE,
            name="Laptop diagnostics and repair",
            slug="laptop-diagnostics-repair",
            short_description="Professional computer diagnosis and repair support.",
            price=Decimal("50000"),
            track_inventory=False,
            is_published=True,
            is_featured=True,
        )

    def test_homepage_renders_marketplace_discovery_architecture(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "market-global-search")
        self.assertContains(response, "All categories")
        self.assertContains(response, "Shop by purpose")
        self.assertContains(response, "Shop by budget")
        self.assertContains(response, "New arrivals")
        self.assertContains(response, "Refurbished technology")
        self.assertContains(response, "HP")
        self.assertContains(response, "marketplace_experience.css")
        self.assertContains(response, "marketplace_experience.js")

    def test_catalogue_filters_brand_condition_and_price(self):
        response = self.client.get(
            reverse("product_list"),
            {
                "kind": "physical",
                "brand": "HP",
                "condition": ProductGrowthData.CONDITION_REFURBISHED,
                "min_price": "1000000",
                "max_price": "2000000",
                "available": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        products = [card.product for card in response.context["products"]]
        self.assertEqual(products, [self.hp])
        self.assertContains(response, self.hp.name)
        self.assertNotContains(response, self.dell.name)
        self.assertContains(response, "Brand: HP")
        self.assertContains(response, "Condition: Refurbished")

    def test_deals_collection_uses_genuine_comparison_price(self):
        response = self.client.get(
            reverse("product_list"),
            {"collection": "deals"},
        )

        self.assertEqual(response.status_code, 200)
        product_ids = {card.pk for card in response.context["products"]}
        self.assertIn(self.hp.pk, product_ids)
        self.assertNotIn(self.dell.pk, product_ids)
        self.assertContains(response, "UGX 1,200,000")
        self.assertContains(response, "UGX 1,500,000")
        self.assertEqual(response.context["products"][0].savings_percent, 20)

    def test_business_collection_searches_product_content(self):
        response = self.client.get(
            reverse("product_list"),
            {"collection": "business"},
        )

        self.assertEqual(response.status_code, 200)
        product_ids = {card.pk for card in response.context["products"]}
        self.assertIn(self.hp.pk, product_ids)
        self.assertIn(self.dell.pk, product_ids)

    def test_public_navigation_exposes_category_counts(self):
        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shop by department")
        self.assertContains(response, "Laptops")
        self.assertContains(response, "2 items")

    def test_product_proxy_exposes_condition_brand_and_savings(self):
        response = self.client.get(reverse("product_list"), {"brand": "HP"})
        card = response.context["products"][0]

        self.assertEqual(card.public_brand, "HP")
        self.assertEqual(card.public_condition, "Refurbished")
        self.assertEqual(card.public_price, Decimal("1200000"))
        self.assertEqual(card.public_compare_at_price, Decimal("1500000"))
        self.assertEqual(card.savings_percent, 20)
