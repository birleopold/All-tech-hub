"""A private completed-order link may never access another order's draft review."""
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductReview
from commerce.models import Order, OrderLine
from crm.models import Customer


@override_settings(SECURE_SSL_REDIRECT=False)
class VerifiedOrderReviewIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(
            name="Multiple orders customer", email="same-review-buyer@example.com",
        )
        category = Category.objects.create(
            name="Review test computers", slug="order-review-isolation-computers",
        )
        cls.product = Product.objects.create(
            category=category, name="Reviewed workstation",
            slug="review-isolation-workstation", price=850000,
            stock_quantity=3, is_published=True,
        )
        cls.service = Product.objects.create(
            category=category, name="Review-only installation service",
            slug="review-isolation-service", kind=Product.KIND_SERVICE,
            price=35000, is_published=True,
        )
        cls.first = Order.objects.create(
            reference="REV-ORDER-ONE", customer=customer,
            status=Order.STATUS_DELIVERED, contact_name="Primary buyer",
            contact_email=customer.email, total=850000,
        )
        cls.second = Order.objects.create(
            reference="REV-ORDER-TWO", customer=customer,
            status=Order.STATUS_FULFILLED, contact_name="Other purchase",
            contact_email=customer.email, total=850000,
        )
        cls.pending = Order.objects.create(
            reference="REV-ORDER-PEND", customer=customer,
            status=Order.STATUS_PENDING, contact_name="Pending buyer",
            contact_email=customer.email, total=850000,
        )
        for order in (cls.first, cls.second, cls.pending):
            OrderLine.objects.create(
                order=order, product=cls.product, description=cls.product.name,
                quantity=1, unit_price=cls.product.price,
            )
        OrderLine.objects.create(
            order=cls.first, product=cls.service,
            description=cls.service.name, quantity=1, unit_price=35000,
        )

    def url(self, order, product=None):
        return reverse("order_product_review", kwargs={
            "reference": order.reference, "view_key": order.view_key,
            "product_id": (product or self.product).pk,
        })

    def test_two_orders_for_same_customer_have_independent_private_reviews(self):
        first = self.client.post(self.url(self.first), {
            "rating": "5", "title": "First purchase", "body": "First order private feedback.",
        })
        self.assertEqual(first.status_code, 302)
        first_review = ProductReview.objects.get(verified_order=self.first, product=self.product)
        self.assertFalse(first_review.is_published)
        self.assertTrue(first_review.is_verified_purchase)

        other_page = self.client.get(self.url(self.second))
        self.assertEqual(other_page.status_code, 200)
        self.assertNotContains(other_page, "First order private feedback.")
        self.assertIsNone(other_page.context["existing_review"])

        second = self.client.post(self.url(self.second), {
            "rating": "3", "title": "Second purchase", "body": "Second order feedback.",
        })
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            ProductReview.objects.filter(product=self.product, is_verified_purchase=True).count(), 2
        )
        self.client.post(self.url(self.first), {
            "rating": "4", "title": "Updated first", "body": "Updated the first order only.",
        })
        first_review.refresh_from_db()
        second_review = ProductReview.objects.get(verified_order=self.second)
        self.assertEqual(first_review.rating, 4)
        self.assertEqual(second_review.rating, 3)
        self.assertEqual(second_review.body, "Second order feedback.")

    def test_legacy_verified_review_is_not_exposed_on_new_order(self):
        legacy = ProductReview.objects.create(
            product=self.product, customer=self.first.customer,
            author_name="Legacy buyer", is_verified_purchase=True,
            body="Confidential historical feedback", rating=1,
        )
        response = self.client.get(self.url(self.first))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Confidential historical feedback")
        self.client.post(self.url(self.first), {
            "rating": "5", "body": "This specific order was great.",
        })
        legacy.refresh_from_db()
        self.assertEqual(legacy.body, "Confidential historical feedback")
        self.assertIsNone(legacy.verified_order_id)
        self.assertEqual(ProductReview.objects.filter(product=self.product).count(), 2)

    def test_unfinished_orders_and_service_items_cannot_be_reviewed(self):
        blocked = self.client.post(self.url(self.pending), {
            "rating": "5", "body": "Not delivered",
        })
        self.assertEqual(blocked.status_code, 302)
        self.assertFalse(ProductReview.objects.filter(verified_order=self.pending).exists())
        invalid_service = self.client.post(self.url(self.first, self.service), {
            "rating": "5", "body": "Service was completed",
        })
        self.assertEqual(invalid_service.status_code, 200)
        self.assertFalse(ProductReview.objects.filter(product=self.service).exists())

    def test_wrong_order_key_is_not_valid_evidence(self):
        invalid = reverse("order_product_review", kwargs={
            "reference": self.first.reference,
            "view_key": self.second.view_key,
            "product_id": self.product.pk,
        })
        self.assertEqual(self.client.get(invalid).status_code, 404)

    def test_database_prevents_duplicate_order_product_review(self):
        review = ProductReview.objects.create(
            product=self.product, customer=self.first.customer,
            verified_order=self.first, is_verified_purchase=True,
            rating=5, body="Original",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductReview.objects.create(
                    product=self.product, customer=self.first.customer,
                    verified_order=self.first, is_verified_purchase=True,
                    rating=1, body="Duplicate",
                )
        self.assertEqual(ProductReview.objects.filter(
            verified_order=self.first, product=self.product
        ).count(), 1)
        self.assertEqual(review.body, "Original")
