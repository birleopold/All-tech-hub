from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from catalog.management.commands.populate_product_categories import CATEGORY_TREE
from catalog.models import Category


class PopulateProductCategoriesTests(TestCase):
    def test_command_creates_main_categories_and_subcategories(self):
        call_command("populate_product_categories", stdout=StringIO())

        expected_main = len(CATEGORY_TREE)
        expected_subcategories = sum(len(children) for _, _, children in CATEGORY_TREE)

        self.assertEqual(Category.objects.filter(parent__isnull=True).count(), expected_main)
        self.assertEqual(
            Category.objects.filter(parent__isnull=False).count(),
            expected_subcategories,
        )
        self.assertTrue(
            Category.objects.filter(
                slug="laptops-business-laptops",
                parent__slug="laptops",
            ).exists()
        )

    def test_command_is_idempotent(self):
        call_command("populate_product_categories", stdout=StringIO())
        first_count = Category.objects.count()

        call_command("populate_product_categories", stdout=StringIO())

        self.assertEqual(Category.objects.count(), first_count)

    def test_dry_run_rolls_back_changes(self):
        call_command("populate_product_categories", "--dry-run", stdout=StringIO())

        self.assertEqual(Category.objects.count(), 0)

    def test_main_only_creates_exactly_fifteen_categories(self):
        call_command("populate_product_categories", "--main-only", stdout=StringIO())

        self.assertEqual(Category.objects.count(), 15)
        self.assertFalse(Category.objects.filter(parent__isnull=False).exists())
