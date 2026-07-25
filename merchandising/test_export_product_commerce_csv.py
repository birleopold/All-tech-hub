from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Category, Product
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


@override_settings(PUBLIC_BASE_URL="https://example.test")
class ExportProductCommerceCsvTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Laptops", slug="laptops")
        self.product = Product.objects.create(
            category=category,
            kind=Product.KIND_PHYSICAL,
            name="Dell Latitude Review Unit",
            slug="dell-latitude-review-unit",
            sku="DL-REVIEW",
            short_description="A reviewed business laptop.",
            description="Detailed reviewed laptop description.",
            price=Decimal("1500000"),
            stock_quantity=2,
            is_published=True,
            is_featured=True,
        )
        ProductGrowthData.objects.create(
            product=self.product,
            brand="Dell",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
            mpn="DL-REVIEW-MPN",
        )
        verified_at = timezone.now()
        ProductCommerceProfile.objects.create(
            product=self.product,
            processor_family="Intel Core i5",
            processor_generation="10th Gen",
            ram_capacity="16GB",
            storage_capacity="512GB",
            storage_type="SSD",
            condition_notes="Tested refurbished product.",
            actual_photos=True,
            identity_verified_at=verified_at,
            condition_verified_at=verified_at,
            stock_confirmed_at=verified_at,
            price_verified_at=verified_at,
            merchant_free_shipping=True,
        )
        Product.objects.create(
            category=category,
            kind=Product.KIND_PHYSICAL,
            name="Hidden Laptop",
            slug="hidden-laptop",
            price=Decimal("500000"),
            stock_quantity=1,
            is_published=False,
        )

    def test_exports_review_ready_round_trip_csv(self):
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "review.csv"
            call_command(
                "export_product_commerce_csv",
                output=str(output),
                limit=30,
            )

            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["sku"], "DL-REVIEW")
            self.assertEqual(row["product_name"], self.product.name)
            self.assertEqual(row["brand"], "Dell")
            self.assertEqual(row["condition"], "refurbished")
            self.assertEqual(row["available_to_sell"], "true")
            self.assertEqual(
                row["product_url"],
                "https://example.test/catalog/item/dell-latitude-review-unit/",
            )
            self.assertIn("merchant approval", row["missing_fields"])

            call_command(
                "import_product_commerce_csv",
                str(output),
                dry_run=True,
            )

    def test_limit_zero_can_include_unpublished_products(self):
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "all-products.csv"
            call_command(
                "export_product_commerce_csv",
                output=str(output),
                limit=0,
                include_unpublished=True,
                order="name",
            )

            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["product_name"] for row in rows],
                ["Dell Latitude Review Unit", "Hidden Laptop"],
            )
