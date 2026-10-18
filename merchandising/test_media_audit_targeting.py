"""Product-specific media audits do not alter product records."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Product


class MediaAuditTargetingTests(TestCase):
    def test_product_id_scope_excludes_other_catalogue_items(self):
        category = Category.objects.create(name="Media diagnostics", slug="media-diag")
        first = Product.objects.create(category=category, name="First test product",
                                       slug="first-media-diag", price="100.00")
        Product.objects.create(category=category, name="Second test product",
                               slug="second-media-diag", price="100.00")
        output = StringIO()
        call_command("audit_catalog_media", product_id=first.pk,
                     skip_hashes=True, stdout=output)
        self.assertIn("Audited 0 product image references", output.getvalue())
        self.assertEqual(Product.objects.count(), 2)
