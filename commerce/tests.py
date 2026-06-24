import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from commerce import cart as cart_mod
from commerce.fulfillment import transition_order
from commerce.models import (
    Coupon,
    CustomerReturn,
    Order,
    OrderStatusEvent,
    OrderStockRestoration,
    Shipment,
)
from commerce.stock import InsufficientStock, decrement_line_stock
from crm.models import Customer


class OrderFulfillmentTests(TestCase):
    def test_default_fulfillment_is_delivery(self):
        c = Customer.objects.create(name="C", email="c@example.com")
        o = Order.objects.create(
            reference="ORD-TEST-1",
            customer=c,
            contact_name="C",
            contact_email="c@example.com",
            subtotal=0,
            tax_amount=0,
            total=0,
        )
        self.assertEqual(o.fulfillment_type, Order.FULFILLMENT_DELIVERY)

    def setUp(self):
        self.category = Category.objects.create(name="Fulfillment", slug="fulfillment")
        self.product = Product.objects.create(
            category=self.category,
            name="Fulfillment item",
            slug="fulfillment-item",
            price=Decimal("10"),
            stock_quantity=3,
        )
        self.customer = Customer.objects.create(
            name="Fulfillment buyer", email="fulfillment@example.com"
        )
        self.order = Order.objects.create(
            reference="ORD-FULFILL",
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
        )
        self.order.lines.create(
            product=self.product,
            description=self.product.name,
            quantity=2,
            unit_price=Decimal("10"),
        )
        self.user = User.objects.create_user("fulfiller", password="pw", is_staff=True)

    def test_valid_status_flow_creates_history(self):
        transition_order(self.order, Order.STATUS_CONFIRMED, actor=self.user)
        transition_order(self.order, Order.STATUS_PROCESSING, actor=self.user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PROCESSING)
        self.assertEqual(OrderStatusEvent.objects.filter(order=self.order).count(), 2)

    def test_invalid_status_jump_is_rejected(self):
        with self.assertRaises(ValidationError):
            transition_order(self.order, Order.STATUS_DELIVERED, actor=self.user)

    def test_cancellation_restores_stock_once(self):
        self.product.stock_quantity = 1
        self.product.save(update_fields=["stock_quantity"])
        transition_order(
            self.order,
            Order.STATUS_CANCELLED,
            actor=self.user,
            note="Customer request",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertTrue(OrderStockRestoration.objects.filter(order=self.order).exists())
        transition_order(self.order, Order.STATUS_CANCELLED, actor=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_staff_order_list_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("staff_orders"))
        self.assertEqual(response.status_code, 200)

    def test_shipment_update_advances_order(self):
        transition_order(self.order, Order.STATUS_CONFIRMED, actor=self.user)
        transition_order(self.order, Order.STATUS_PROCESSING, actor=self.user)
        transition_order(self.order, Order.STATUS_READY, actor=self.user)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_order_shipment", args=[self.order.pk]),
            {
                "carrier": "Demo Courier",
                "tracking_number": "TRACK-1",
                "tracking_url": "https://carrier.example/TRACK-1",
                "status": Shipment.STATUS_IN_TRANSIT,
                "estimated_delivery": "2026-06-30",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_DISPATCHED)


class CartLineKeyTests(TestCase):
    def setUp(self):
        self.session = SessionStore()
        self.session.create()

    def tearDown(self):
        self.session.flush()

    def test_normalize_legacy_numeric_key(self):
        self.assertEqual(cart_mod.normalize_line_key("42"), ("p", 42))

    def test_normalize_prefixed_keys(self):
        self.assertEqual(cart_mod.normalize_line_key("p:7"), ("p", 7))
        self.assertEqual(cart_mod.normalize_line_key("v:99"), ("v", 99))

    def test_iter_skips_plain_product_when_variants_exist(self):
        cat = Category.objects.create(name="Cat", slug="cat")
        product = Product.objects.create(
            category=cat,
            name="Multi",
            slug="multi",
            price=Decimal("10.00"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=10,
        )
        ProductVariant.objects.create(
            product=product,
            name="A",
            price=Decimal("12.00"),
            stock_quantity=3,
        )
        session = self.session
        cart_mod.set_cart(session, {str(product.pk): 2})
        lines = list(cart_mod.iter_cart_lines(session))
        self.assertEqual(lines, [])

    def test_iter_yields_variant_line(self):
        cat = Category.objects.create(name="Cat2", slug="cat2")
        product = Product.objects.create(
            category=cat,
            name="Multi2",
            slug="multi2",
            price=Decimal("10.00"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=0,
        )
        v = ProductVariant.objects.create(
            product=product,
            name="B",
            price=Decimal("15.00"),
            stock_quantity=4,
        )
        session = self.session
        cart_mod.add_variant(session, v.pk, 2)
        lines = list(cart_mod.iter_cart_lines(session))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].variant.pk, v.pk)
        self.assertEqual(lines[0].quantity, 2)
        self.assertEqual(lines[0].unit_price, Decimal("15.00"))


class CartInputSecurityTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Safe", slug="safe-cart")
        self.product = Product.objects.create(
            category=self.category,
            name="Safe item",
            slug="safe-item",
            price=Decimal("10"),
            stock_quantity=5,
        )

    def test_malformed_quantity_does_not_crash(self):
        response = self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {"quantity": "not-a-number"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session[cart_mod.CART_SESSION_KEY][f"p:{self.product.pk}"], 1)

    def test_external_next_url_is_rejected(self):
        response = self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {"quantity": "1", "next": "https://evil.example/steal"},
        )
        self.assertRedirects(response, self.product.get_absolute_url())


class StockDecrementTests(TestCase):
    def test_decrement_blocks_overdraw(self):
        cat = Category.objects.create(name="C", slug="c-stock")
        product = Product.objects.create(
            category=cat,
            name="P",
            slug="p-stock",
            price=Decimal("5.00"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=1,
            track_inventory=True,
        )
        with self.assertRaises(InsufficientStock):
            decrement_line_stock(product=product, variant=None, qty=2)

    def test_decrement_updates_product_stock(self):
        cat = Category.objects.create(name="C2", slug="c-stock2")
        product = Product.objects.create(
            category=cat,
            name="P2",
            slug="p-stock2",
            price=Decimal("5.00"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=4,
            track_inventory=True,
        )
        decrement_line_stock(product=product, variant=None, qty=2)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 2)


class OrderReceiptUrlTests(TestCase):
    def test_public_receipt_requires_matching_view_key(self):
        c = Customer.objects.create(name="C", email="c@example.com")
        order = Order.objects.create(
            reference="ORD-REC-1",
            customer=c,
            contact_name="C",
            contact_email="c@example.com",
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            total=Decimal("0"),
        )
        client = Client()
        bad = client.get(
            reverse(
                "order_detail",
                kwargs={"reference": order.reference, "view_key": uuid.uuid4()},
            )
        )
        self.assertEqual(bad.status_code, 404)
        ok = client.get(
            reverse(
                "order_detail",
                kwargs={"reference": order.reference, "view_key": order.view_key},
            )
        )
        self.assertEqual(ok.status_code, 200)


class CheckoutStockAndTokenTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Category.objects.create(name="Cat", slug="cat-chk")
        self.product = Product.objects.create(
            category=self.cat,
            name="Stocky",
            slug="stocky-chk",
            sku="STK-CH",
            price=Decimal("10"),
            stock_quantity=1,
        )

    def _checkout_post_data(self, token: str) -> dict:
        return {
            "name": "Buyer",
            "email": "buyer@example.com",
            "phone": "",
            "company_name": "",
            "billing_address": "123 St",
            "shipping_address": "",
            "customer_note": "",
            "fulfillment_type": Order.FULFILLMENT_DELIVERY,
            "checkout_token": token,
        }

    def _prime_cart(self, qty: int) -> None:
        self.client.get(reverse("home"))
        r = self.client.post(
            reverse("cart_add", kwargs={"product_id": self.product.pk}),
            {"quantity": qty},
        )
        self.assertEqual(r.status_code, 302)
        rc = self.client.get(reverse("cart"))
        self.assertEqual(rc.status_code, 200)
        self.assertContains(rc, "Stocky")

    def test_checkout_rejects_oversell(self):
        self._prime_cart(2)
        self.client.get(reverse("checkout"))
        token = self.client.session.get("checkout_submit_token")
        self.assertTrue(token)
        r = self.client.post(
            reverse("checkout"), self._checkout_post_data(token)
        )
        self.assertRedirects(r, reverse("checkout"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_success_decrements_stock(self):
        self.product.stock_quantity = 5
        self.product.save(update_fields=["stock_quantity"])
        self._prime_cart(2)
        self.client.get(reverse("checkout"))
        token = self.client.session["checkout_submit_token"]
        r = self.client.post(
            reverse("checkout"), self._checkout_post_data(token)
        )
        order = Order.objects.get()
        self.assertRedirects(
            r,
            reverse(
                "order_detail",
                kwargs={"reference": order.reference, "view_key": order.view_key},
            ),
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_checkout_rejects_stale_submit_token(self):
        self._prime_cart(1)
        self.client.get(reverse("checkout"))
        stale = self.client.session["checkout_submit_token"]
        self.client.get(reverse("checkout"))
        self.assertNotEqual(stale, self.client.session["checkout_submit_token"])
        r = self.client.post(
            reverse("checkout"), self._checkout_post_data(stale)
        )
        self.assertRedirects(r, reverse("checkout"))
        self.assertEqual(Order.objects.count(), 0)


class CouponTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Category.objects.create(name="Cat", slug="cat-cp")
        self.product = Product.objects.create(
            category=self.cat,
            name="Coupon Item",
            slug="coupon-item",
            sku="CPN-1",
            price=Decimal("100"),
            stock_quantity=10,
        )
        self.percent = Coupon.objects.create(code="SAVE10", kind="percent", value=Decimal("10"))
        self.fixed = Coupon.objects.create(
            code="OFF20", kind="fixed", value=Decimal("20"), min_subtotal=Decimal("50")
        )

    def _prime_cart(self, qty: int = 1):
        session = self.client.session
        session[cart_mod.CART_SESSION_KEY] = {f"p:{self.product.pk}": qty}
        session.save()

    def test_percent_discount_applied(self):
        self._prime_cart(2)
        self.client.post(reverse("cart_apply_coupon"), {"code": "save10"})
        sess = self.client.session
        subtotal, _tax, total, discount = cart_mod.cart_totals_with_discount(
            sess, Decimal("0")
        )
        self.assertEqual(subtotal, Decimal("200.00"))
        self.assertEqual(discount, Decimal("20.00"))
        self.assertEqual(total, Decimal("180.00"))

    def test_remove_coupon(self):
        self._prime_cart(1)
        self.client.post(reverse("cart_apply_coupon"), {"code": "SAVE10"})
        self.assertTrue(self.client.session.get(cart_mod.COUPON_SESSION_KEY))
        self.client.post(reverse("cart_remove_coupon"))
        self.assertFalse(self.client.session.get(cart_mod.COUPON_SESSION_KEY))

    def test_invalid_coupon_not_stored(self):
        self._prime_cart(1)
        self.client.post(reverse("cart_apply_coupon"), {"code": "NOPE"})
        self.assertFalse(self.client.session.get(cart_mod.COUPON_SESSION_KEY))

    def test_min_subtotal_enforced(self):
        self._prime_cart(1)
        self.client.post(reverse("cart_apply_coupon"), {"code": "OFF20"})
        self.assertEqual(
            self.client.session.get(cart_mod.COUPON_SESSION_KEY), "OFF20"
        )

    def test_inactive_coupon_rejected(self):
        self.percent.is_active = False
        self.percent.save(update_fields=["is_active"])
        self._prime_cart(1)
        self.client.post(reverse("cart_apply_coupon"), {"code": "SAVE10"})
        self.assertFalse(self.client.session.get(cart_mod.COUPON_SESSION_KEY))


class CustomerReturnTests(TestCase):
    def test_restock_return_creates_movement(self):
        from django.contrib.auth.models import User

        from inventory.models import StockMovement

        category = Category.objects.create(name="Returns", slug="returns")
        product = Product.objects.create(
            category=category,
            name="Returned item",
            slug="returned-item",
            price=Decimal("10"),
            stock_quantity=0,
        )
        customer = Customer.objects.create(name="Buyer", email="return@example.com")
        order = Order.objects.create(
            reference="ORD-RETURN",
            customer=customer,
            contact_name="Buyer",
            contact_email=customer.email,
            total=Decimal("20"),
        )
        line = order.lines.create(
            product=product,
            description=product.name,
            quantity=2,
            unit_price=Decimal("10"),
        )
        user = User.objects.create_user("returns", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.post(
            reverse("staff_order_return", args=[order.pk]),
            {
                "order_line": line.pk,
                "quantity": 1,
                "reason": "Changed mind",
                "disposition": CustomerReturn.DISPOSITION_RESTOCK,
            },
        )
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 1)
        self.assertTrue(
            StockMovement.objects.filter(
                movement_type=StockMovement.TYPE_CUSTOMER_RETURN
            ).exists()
        )
