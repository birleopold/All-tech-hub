"""Only sellable tracked SKUs may appear in the approved product feed."""
from unittest.mock import PropertyMock, patch
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from merchandising.models import ProductCommerceProfile


class ApprovedFeedInventoryTests(TestCase):
    def test_sold_out_variant_is_not_exported(self):
        category = Category.objects.create(name="Tracked feed", slug="tracked-feed-guard")
        product = Product.objects.create(
            category=category, name="Example configurable laptop",
            slug="tracked-feed-example", sku="BASE-STOCK-GUARD",
            price="125000.00", is_published=True, track_inventory=True,
            stock_quantity=0,
        )
        ProductVariant.objects.create(
            product=product, name="In stock", sku="IN-STOCK-GUARD",
            price="125000.00", track_inventory=True, stock_quantity=2,
        )
        ProductVariant.objects.create(
            product=product, name="Sold out", sku="SOLD-OUT-GUARD",
            price="125000.00", track_inventory=True, stock_quantity=0,
        )
        ProductCommerceProfile.objects.create(product=product, merchant_enabled=True)
        feed = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<rss xmlns:g="http://base.google.com/ns/1.0"><channel>'
                b'<item><g:id>IN-STOCK-GUARD</g:id></item>'
                b'<item><g:id>SOLD-OUT-GUARD</g:id></item>'
                b'</channel></rss>')
        with patch("merchandising.merchant.base_strict_feed",
                   return_value=HttpResponse(feed, content_type="application/rss+xml")), patch.object(
                       ProductCommerceProfile, "is_merchant_ready",
                       new_callable=PropertyMock, return_value=True):
            response = self.client.get(reverse("google_approved_merchant_feed"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"IN-STOCK-GUARD", response.content)
        self.assertNotIn(b"SOLD-OUT-GUARD", response.content)
        self.assertEqual(response["X-Merchant-Eligible-Items"], "1")
