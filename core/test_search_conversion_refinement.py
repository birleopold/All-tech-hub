from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from growth.models import ProductGrowthData


class SearchConversionRefinementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.laptops = Category.objects.create(
            name="Laptops",
            slug="search-laptops",
            description="Portable computers for work and learning.",
        )
        cls.accessories = Category.objects.create(
            name="Accessories",
            slug="search-accessories",
            description="Computer accessories and essentials.",
            sort_order=2,
        )
        cls.hp = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="HP ProBook 440 G2",
            slug="search-hp-probook-440-g2",
            sku="HP-440-G2-SEARCH",
            short_description="Core i5 business laptop with 8GB RAM and 256GB SSD storage.",
            description="A dependable office and student computer.",
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
        cls.hp_related = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="HP EliteBook 840 G5",
            slug="search-hp-elitebook-840-g5",
            sku="HP-840-G5-SEARCH",
            short_description="Core i5 professional laptop with 8GB RAM and SSD.",
            price=Decimal("1800000"),
            stock_quantity=2,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.hp_related,
            brand="HP",
            condition=ProductGrowthData.CONDITION_USED,
        )
        cls.variant_product = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="Dell Latitude Configurable Laptop",
            slug="search-dell-configurable-laptop",
            sku="DELL-CONFIG-SEARCH",
            short_description="A business laptop offered in multiple configurations.",
            price=Decimal("5000000"),
            stock_quantity=10,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.variant_product,
            brand="Dell",
            condition=ProductGrowthData.CONDITION_NEW,
        )
        ProductVariant.objects.create(
            product=cls.variant_product,
            name="8GB / 256GB",
            sku="DELL-8-256",
            price=Decimal("1500000"),
            stock_quantity=2,
            is_active=True,
        )
        ProductVariant.objects.create(
            product=cls.variant_product,
            name="16GB / 512GB",
            sku="DELL-16-512",
            price=Decimal("3000000"),
            stock_quantity=1,
            is_active=True,
        )
        cls.variant_out_of_stock = Product.objects.create(
            category=cls.laptops,
            kind=Product.KIND_PHYSICAL,
            name="Lenovo Variant Stock Test",
            slug="search-lenovo-variant-stock-test",
            sku="LENOVO-OOS-SEARCH",
            short_description="Variant-managed business laptop.",
            price=Decimal("1700000"),
            stock_quantity=9,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.variant_out_of_stock,
            brand="Lenovo",
            condition=ProductGrowthData.CONDITION_USED,
        )
        ProductVariant.objects.create(
            product=cls.variant_out_of_stock,
            name="8GB / 256GB",
            sku="LENOVO-OOS-VARIANT",
            price=Decimal("1700000"),
            stock_quantity=0,
            track_inventory=True,
            is_active=True,
        )
        cls.service = Product.objects.create(
            category=cls.accessories,
            kind=Product.KIND_SERVICE,
            name="Laptop diagnostics",
            slug="search-laptop-diagnostics",
            short_description="Professional diagnosis and repair guidance.",
            price=Decimal("50000"),
            track_inventory=False,
            is_published=True,
        )

    def test_multi_word_search_requires_each_term_and_orders_by_relevance(self):
        response = self.client.get(
            reverse("product_list"),
            {"q": "HP 8GB SSD"},
        )

        self.assertEqual(response.status_code, 200)
        product_ids = [card.pk for card in response.context["products"]]
        self.assertEqual(product_ids[0], self.hp.pk)
        self.assertIn(self.hp_related.pk, product_ids)
        self.assertNotIn(self.variant_product.pk, product_ids)
        self.assertEqual(response.context["current_sort"], "relevance")
        self.assertContains(response, "Best matches first")

    def test_variant_price_filter_and_sort_use_displayed_from_price(self):
        within_budget = self.client.get(
            reverse("product_list"),
            {"brand": "Dell", "max_price": "2000000"},
        )
        above_budget = self.client.get(
            reverse("product_list"),
            {"brand": "Dell", "min_price": "2000000"},
        )

        self.assertIn(
            self.variant_product.pk,
            {card.pk for card in within_budget.context["products"]},
        )
        self.assertNotIn(
            self.variant_product.pk,
            {card.pk for card in above_budget.context["products"]},
        )
        card = within_budget.context["products"][0]
        self.assertEqual(card.public_price, Decimal("1500000"))

    def test_available_filter_respects_active_variant_stock(self):
        response = self.client.get(reverse("product_list"), {"available": "1"})
        product_ids = {card.pk for card in response.context["products"]}

        self.assertIn(self.hp.pk, product_ids)
        self.assertIn(self.variant_product.pk, product_ids)
        self.assertIn(self.service.pk, product_ids)
        self.assertNotIn(self.variant_out_of_stock.pk, product_ids)

    def test_search_suggestions_return_products_categories_and_brands(self):
        response = self.client.get(
            reverse("catalog_suggestions"),
            {"q": "HP"},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["products"][0]["name"], self.hp.name)
        self.assertTrue(any(row["name"] == "HP" for row in payload["brands"]))
        self.assertIn("public", response.headers["Cache-Control"])
        self.assertIn("q=HP", payload["search_url"])

    def test_active_filter_removal_keeps_other_filters(self):
        response = self.client.get(
            reverse("product_list"),
            {
                "brand": "HP",
                "condition": ProductGrowthData.CONDITION_REFURBISHED,
                "max_price": "2000000",
            },
        )
        brand_filter = next(
            item
            for item in response.context["active_filter_items"]
            if item["label"] == "Brand: HP"
        )

        self.assertNotIn("brand=", brand_filter["remove_url"])
        self.assertIn("condition=refurbished", brand_filter["remove_url"])
        self.assertIn("max_price=2000000", brand_filter["remove_url"])

    def test_product_detail_exposes_related_products_and_retail_schema(self):
        response = self.client.get(self.hp.get_absolute_url())
        related_ids = {card.pk for card in response.context["related_products"]}

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.hp_related.pk, related_ids)
        self.assertContains(response, "Similar products and services")
        self.assertContains(response, "BreadcrumbList")
        self.assertContains(response, "Save 20%")

    def test_recently_viewed_products_continue_on_homepage(self):
        self.client.get(self.hp.get_absolute_url())
        response = self.client.get(reverse("home"))

        self.assertEqual(response.context["recently_viewed_products"][0].pk, self.hp.pk)
        self.assertContains(response, "Recently viewed")
        self.assertContains(response, self.hp.name)

    def test_simple_available_cards_offer_quick_add(self):
        response = self.client.get(reverse("product_list"), {"brand": "HP"})

        self.assertContains(response, "data-market-quick-add")
        self.assertContains(response, reverse("cart_add", args=[self.hp.pk]))

    def test_no_results_offer_available_recommendations(self):
        response = self.client.get(
            reverse("product_list"),
            {"q": "no-such-catalogue-item-xyz"},
        )

        self.assertEqual(response.context["products"], [])
        self.assertTrue(response.context["fallback_products"])
        self.assertContains(response, "Popular available alternatives")

    def test_public_pages_include_search_and_item_list_schema(self):
        home = self.client.get(reverse("home"))
        catalogue = self.client.get(reverse("product_list"))

        self.assertContains(home, "SearchAction")
        self.assertContains(home, "search_conversion_refinement.css")
        self.assertContains(home, "data-market-search-form")
        self.assertContains(catalogue, "ItemList")
        self.assertContains(catalogue, "BreadcrumbList")
