from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from django.contrib.auth.models import User

from catalog.models import (
    Category,
    Product,
    ProductReview,
    ProductSerial,
    WishlistItem,
    product_review_summary,
)
from crm.models import Customer


class ProductReviewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Reviewable", slug="reviewable")
        self.product = Product.objects.create(
            category=self.category,
            name="Reviewable Item",
            slug="reviewable-item",
            sku="REV-1",
            price=Decimal("100"),
            stock_quantity=5,
            is_published=True,
        )
        self.client = Client()

    def test_summary_ignores_unpublished_reviews(self):
        ProductReview.objects.create(product=self.product, rating=5, body="great", is_published=True)
        ProductReview.objects.create(product=self.product, rating=3, body="meh", is_published=False)
        summary = product_review_summary(self.product)
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["avg"], 5.0)

    def test_submit_review_creates_pending(self):
        url = reverse("product_review_submit", kwargs={"slug": self.product.slug})
        resp = self.client.post(
            url,
            {"author_name": "Pat", "rating": 4, "body": "Solid product."},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        review = ProductReview.objects.get(product=self.product)
        self.assertFalse(review.is_published)
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.author_name, "Pat")

    def test_submit_review_validates_input(self):
        url = reverse("product_review_submit", kwargs={"slug": self.product.slug})
        resp = self.client.post(url, {"rating": 7, "body": ""}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ProductReview.objects.filter(product=self.product).exists())


class WishlistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("wishuser", "w@example.com", "pw")
        self.customer = Customer.objects.create(
            name="Wish", email="w@example.com", user=self.user
        )
        self.category = Category.objects.create(name="Wishable", slug="wishable")
        self.product = Product.objects.create(
            category=self.category,
            name="Wishable Item",
            slug="wishable-item",
            sku="WL-1",
            price=Decimal("50"),
            stock_quantity=2,
            is_published=True,
        )

    def test_add_and_remove_wishlist(self):
        client = Client()
        client.force_login(self.user)
        client.post(reverse("portal_wishlist_add", args=[self.product.pk]))
        self.assertEqual(
            WishlistItem.objects.filter(customer=self.customer, product=self.product).count(),
            1,
        )
        client.post(reverse("portal_wishlist_remove", args=[self.product.pk]))
        self.assertFalse(
            WishlistItem.objects.filter(customer=self.customer, product=self.product).exists()
        )

    def test_wishlist_requires_login(self):
        client = Client()
        r = client.get(reverse("portal_wishlist"))
        self.assertEqual(r.status_code, 302)

    def test_duplicate_wishlist_add_is_idempotent(self):
        client = Client()
        client.force_login(self.user)
        client.post(reverse("portal_wishlist_add", args=[self.product.pk]))
        client.post(reverse("portal_wishlist_add", args=[self.product.pk]))
        self.assertEqual(WishlistItem.objects.filter(customer=self.customer).count(), 1)


class ProductSerialTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Serialized", slug="serialized")
        self.product = Product.objects.create(
            category=self.cat,
            name="Laptop",
            slug="laptop-sn",
            sku="LAP-1",
            price=Decimal("1000"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=1,
        )

    def test_warranty_expiry_when_known(self):
        from datetime import date

        s = ProductSerial.objects.create(
            product=self.product,
            serial_number="SN-001",
            sold_at=date(2025, 1, 15),
            warranty_months=12,
        )
        self.assertEqual(s.warranty_expires_on, date(2026, 1, 15))

    def test_warranty_expiry_none_when_no_sale(self):
        s = ProductSerial.objects.create(
            product=self.product,
            serial_number="SN-002",
            warranty_months=12,
        )
        self.assertIsNone(s.warranty_expires_on)
        self.assertFalse(s.is_under_warranty)

    def test_unique_per_product(self):
        from django.db.utils import IntegrityError

        ProductSerial.objects.create(product=self.product, serial_number="DUP")
        with self.assertRaises(IntegrityError):
            ProductSerial.objects.create(product=self.product, serial_number="DUP")


class ApiTests(TestCase):
    def test_products_endpoint_returns_published(self):
        cat = Category.objects.create(name="Api Cat", slug="api-cat")
        Product.objects.create(
            category=cat, name="Visible", slug="visible-api",
            sku="A1", price=Decimal("10"),
            kind=Product.KIND_PHYSICAL,
            is_published=True, stock_quantity=2,
        )
        Product.objects.create(
            category=cat, name="Hidden", slug="hidden-api",
            sku="A2", price=Decimal("10"),
            kind=Product.KIND_PHYSICAL,
            is_published=False, stock_quantity=2,
        )
        r = self.client.get("/api/v1/products/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        names = [p["name"] for p in body["results"]]
        self.assertIn("Visible", names)
        self.assertNotIn("Hidden", names)

    def test_order_lookup_requires_both_params(self):
        r = self.client.get("/api/v1/orders/lookup/?reference=x")
        self.assertEqual(r.status_code, 400)
