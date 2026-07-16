from django.test import TestCase

from catalog.models import Category, Product
from commerce.models import Order, OrderLine
from commerce.recommendations import recommended_products_for_order
from crm.models import Customer


class CommerceRecommendationTests(TestCase):
    def setUp(self):
        self.computers = Category.objects.create(name="Computers", slug="computers")
        self.accessories = Category.objects.create(
            name="Accessories",
            slug="accessories",
        )
        self.customer = Customer.objects.create(
            name="Recommendation Customer",
            email="recommend@example.com",
        )
        self.purchased = Product.objects.create(
            category=self.computers,
            name="Office Laptop",
            slug="office-laptop-recommendation-test",
            price="1200000.00",
            stock_quantity=2,
        )
        self.same_category = Product.objects.create(
            category=self.computers,
            name="Portable Laptop",
            slug="portable-laptop-recommendation-test",
            price="1800000.00",
            stock_quantity=2,
        )
        self.other_category = Product.objects.create(
            category=self.accessories,
            name="Wireless Mouse",
            slug="wireless-mouse-recommendation-test",
            price="80000.00",
            stock_quantity=5,
            is_featured=True,
        )
        self.out_of_stock = Product.objects.create(
            category=self.computers,
            name="Unavailable Laptop",
            slug="unavailable-laptop-recommendation-test",
            price="1000000.00",
            stock_quantity=0,
        )
        self.service = Product.objects.create(
            category=self.computers,
            kind=Product.KIND_SERVICE,
            name="Laptop repair service",
            slug="laptop-repair-recommendation-test",
            price="100000.00",
            track_inventory=False,
        )
        self.order = Order.objects.create(
            reference="ORD-REC-001",
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total=self.purchased.price,
        )
        OrderLine.objects.create(
            order=self.order,
            product=self.purchased,
            description=self.purchased.name,
            quantity=1,
            unit_price=self.purchased.price,
        )

    def test_recommendations_prioritise_same_category_and_exclude_invalid_items(self):
        products = recommended_products_for_order(self.order, limit=4)
        product_ids = [product.pk for product in products]

        self.assertEqual(products[0].pk, self.same_category.pk)
        self.assertIn(self.other_category.pk, product_ids)
        self.assertNotIn(self.purchased.pk, product_ids)
        self.assertNotIn(self.out_of_stock.pk, product_ids)
        self.assertNotIn(self.service.pk, product_ids)

    def test_cancelled_orders_do_not_increase_popularity(self):
        popular = Product.objects.create(
            category=self.accessories,
            name="USB Hub",
            slug="usb-hub-recommendation-test",
            price="150000.00",
            stock_quantity=3,
        )
        cancelled = Order.objects.create(
            reference="ORD-REC-CANCELLED",
            customer=self.customer,
            status=Order.STATUS_CANCELLED,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total=popular.price,
        )
        OrderLine.objects.create(
            order=cancelled,
            product=popular,
            description=popular.name,
            quantity=10,
            unit_price=popular.price,
        )

        products = recommended_products_for_order(self.order, limit=4)
        self.assertEqual(products[0].pk, self.same_category.pk)
