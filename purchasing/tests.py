from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from purchasing.models import (
    PurchaseLine,
    PurchaseOrder,
    StockReceipt,
    StockReceiptLine,
    Supplier,
    SupplierReturn,
)


class ReceivingIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="pw", is_staff=True)
        self.supplier = Supplier.objects.create(name="Supplier")
        category = Category.objects.create(name="PO", slug="po-tests")
        self.product = Product.objects.create(
            category=category,
            name="Ordered item",
            slug="ordered-item",
            price=Decimal("10"),
            stock_quantity=0,
        )
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=self.user
        )
        self.line = PurchaseLine.objects.create(
            purchase_order=self.po,
            product=self.product,
            quantity=2,
            unit_cost=Decimal("5"),
        )
        self.receipt = StockReceipt.objects.create(
            purchase_order=self.po, received_by=self.user
        )

    def test_over_receiving_is_rejected(self):
        receipt_line = StockReceiptLine.objects.create(
            receipt=self.receipt,
            purchase_line=self.line,
            quantity_received=3,
        )
        with self.assertRaises(ValidationError):
            receipt_line.apply()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)

    def test_cross_purchase_order_line_is_rejected(self):
        other_po = PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=self.user
        )
        other_line = PurchaseLine.objects.create(
            purchase_order=other_po,
            product=self.product,
            quantity=1,
            unit_cost=Decimal("5"),
        )
        receipt_line = StockReceiptLine(
            receipt=self.receipt,
            purchase_line=other_line,
            quantity_received=1,
        )
        with self.assertRaises(ValidationError):
            receipt_line.full_clean()

    def test_receipt_line_cannot_be_applied_twice(self):
        receipt_line = StockReceiptLine.objects.create(
            receipt=self.receipt,
            purchase_line=self.line,
            quantity_received=1,
        )
        receipt_line.apply()
        with self.assertRaises(ValidationError):
            receipt_line.apply()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

    def test_supplier_return_reduces_stock(self):
        self.line.received_quantity = 2
        self.line.save(update_fields=["received_quantity"])
        self.product.stock_quantity = 2
        self.product.save(update_fields=["stock_quantity"])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_po_return", args=[self.po.pk]),
            {
                "purchase_line": self.line.pk,
                "quantity": 1,
                "reason": "Faulty shipment",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)
        self.assertEqual(SupplierReturn.objects.count(), 1)

    def test_supplier_returns_reduce_net_received_value_without_rewriting_history(self):
        self.line.received_quantity = 2
        self.line.save(update_fields=["received_quantity"])
        self.product.stock_quantity = 2
        self.product.save(update_fields=["stock_quantity"])
        self.client.force_login(self.user)
        self.assertEqual(self.po.total_received_value, Decimal("10.00"))
        response = self.client.post(
            reverse("staff_po_return", args=[self.po.pk]),
            {
                "purchase_line": self.line.pk,
                "quantity": 1,
                "reason": "Faulty goods",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.po.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(self.line.received_quantity, 2)
        self.assertEqual(self.po.total_received_value, Decimal("10.00"))
        self.assertEqual(self.po.total_returned_value, Decimal("5.00"))
        self.assertEqual(self.po.net_received_value, Decimal("5.00"))
        detail = self.client.get(reverse("staff_po_edit", args=[self.po.pk]))
        self.assertContains(detail, "Net value of goods received")
        self.assertContains(detail, "5.00")

    def test_purchase_order_can_receive_a_partial_shipment(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_po_receive", args=[self.po.pk]),
            {f"quantity_{self.line.pk}": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.po.refresh_from_db()
        self.line.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.STATUS_PARTIAL)
        self.assertEqual(self.line.received_quantity, 1)
        self.assertEqual(self.product.stock_quantity, 1)

    def _po_payload(self, **overrides):
        data = {
            "supplier": str(self.supplier.pk),
            "status": PurchaseOrder.STATUS_PARTIAL,
            "ordered_on": str(self.po.ordered_on),
            "expected_on": "",
            "notes": "Keep delivery history unchanged",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "1",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-id": str(self.line.pk),
            "lines-0-product": str(self.product.pk),
            "lines-0-product_variant": "",
            "lines-0-description": "",
            "lines-0-quantity": "2",
            "lines-0-unit_cost": "5.00",
        }
        data.update(overrides)
        return data

    def test_received_line_original_cost_is_immutable(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("staff_po_receive", args=[self.po.pk]),
            {f"quantity_{self.line.pk}": "1"},
        )
        result = self.client.post(
            reverse("staff_po_edit", args=[self.po.pk]),
            self._po_payload(**{"lines-0-unit_cost": "5000.00"}),
        )
        self.assertEqual(result.status_code, 302)
        self.line.refresh_from_db()
        self.assertEqual(self.line.unit_cost, Decimal("5"))
        self.assertEqual(self.line.received_quantity, 1)

    def test_order_cannot_reduce_quantity_below_received(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("staff_po_receive", args=[self.po.pk]),
            {f"quantity_{self.line.pk}": "2"},
        )
        response = self.client.post(
            reverse("staff_po_edit", args=[self.po.pk]),
            self._po_payload(**{
                "lines-0-quantity": "1",
                "status": PurchaseOrder.STATUS_RECEIVED,
            }),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ordered quantity cannot be below")
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity, 2)

    def test_cannot_change_supplier_once_goods_are_received(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("staff_po_receive", args=[self.po.pk]),
            {f"quantity_{self.line.pk}": "1"},
        )
        other_supplier = Supplier.objects.create(name="Not original supplier")
        result = self.client.post(
            reverse("staff_po_edit", args=[self.po.pk]),
            self._po_payload(supplier=str(other_supplier.pk)),
        )
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Cannot change the supplier")
        self.po.refresh_from_db()
        self.assertEqual(self.po.supplier_id, self.supplier.pk)

    def test_partial_receiving_rejects_quantities_above_remaining(self):
        self.client.force_login(self.user)
        receipt_count = StockReceipt.objects.count()
        response = self.client.post(
            reverse("staff_po_receive", args=[self.po.pk]),
            {f"quantity_{self.line.pk}": "3"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockReceipt.objects.count(), receipt_count)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)
