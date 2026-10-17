from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument, CommercialLine
from catalog.models import Category, Product, ProductSerial, ProductVariant
from core.models import AuditEvent, SupportTicket
from crm.models import Customer
from inventory.forms import JobStockUseForm
from inventory.models import StockAdjustment, StockMovement, StockTake, StockTakeLine
from operations.models import JobCard


class JobStockUseFormTests(TestCase):
    def test_rejects_non_negative_quantity(self):
        cat = Category.objects.create(name="C", slug="c-inv")
        p = Product.objects.create(
            category=cat,
            name="Part",
            slug="part-inv",
            price=Decimal("5"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=5,
        )
        form = JobStockUseForm(
            data={
                "product": p.pk,
                "product_variant": "",
                "quantity_delta": "1",
                "note": "",
            }
        )
        self.assertFalse(form.is_valid())

    def test_same_adjustment_cannot_move_stock_twice(self):
        category = Category.objects.create(name="Idempotent", slug="idempotent-adjustment")
        product = Product.objects.create(
            category=category, name="One-time part", slug="one-time-part",
            price=Decimal("10"), stock_quantity=5,
        )
        adjustment = StockAdjustment.objects.create(
            product=product, quantity_delta=-2,
            reason=StockAdjustment.REASON_JOB,
        )
        adjustment.apply()
        with self.assertRaisesMessage(ValidationError, "already been applied"):
            adjustment.apply()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 3)
        self.assertEqual(
            StockMovement.objects.filter(adjustment=adjustment).count(), 1
        )

    def test_adjustment_cannot_make_stock_negative(self):
        cat = Category.objects.create(name="Guard", slug="guard-stock")
        product = Product.objects.create(
            category=cat,
            name="Guarded part",
            slug="guarded-part",
            price=Decimal("5"),
            stock_quantity=1,
        )
        adjustment = StockAdjustment.objects.create(
            product=product,
            quantity_delta=-2,
            reason=StockAdjustment.REASON_DAMAGE,
        )
        with self.assertRaises(ValidationError):
            adjustment.apply()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 1)
        self.assertFalse(StockMovement.objects.filter(product=product).exists())


class JobPartUsageViewTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="C2", slug="c2-inv")
        self.product = Product.objects.create(
            category=self.cat,
            name="Screen",
            slug="screen-inv",
            price=Decimal("99"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=10,
        )
        self.customer = Customer.objects.create(name="Walk-in", email="w@example.com")
        self.job = JobCard.objects.create(
            customer=self.customer,
            title="Replace screen",
            status=JobCard.STATUS_INTAKE,
        )
        self.user = User.objects.create_user("inv", "inv@example.com", "pw", is_staff=True)

    def test_completed_job_rejects_new_part_usage(self):
        self.job.status = JobCard.STATUS_COMPLETED
        self.job.save(update_fields=["status"])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_job_stock_use", args=[self.job.pk]),
            {
                "product": self.product.pk,
                "product_variant": "",
                "quantity_delta": "-2",
                "note": "Too late",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertFalse(StockAdjustment.objects.filter(job=self.job).exists())

    def test_post_records_adjustment_and_stock(self):
        self.client.force_login(self.user)
        url = reverse("staff_job_stock_use", args=[self.job.pk])
        response = self.client.post(
            url,
            {
                "product": self.product.pk,
                "product_variant": "",
                "quantity_delta": "-2",
                "note": "Used on bench",
            },
        )
        self.assertRedirects(response, reverse("staff_job_detail", args=[self.job.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        adj = StockAdjustment.objects.get(job=self.job)
        movement = StockMovement.objects.get(adjustment=adj)
        self.assertEqual(movement.balance_after, 8)
        self.assertEqual(adj.quantity_delta, -2)
        self.assertEqual(adj.reason, StockAdjustment.REASON_JOB)
        self.assertTrue(
            AuditEvent.objects.filter(verb="inventory.job_part_use").exists()
        )


class LabelSheetViewTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Labels", slug="labels")
        self.product = Product.objects.create(
            category=self.cat,
            name="Label printer",
            slug="label-printer",
            sku="LP-100",
            price=Decimal("250"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=4,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="USB",
            sku="LP-100-USB",
            price=Decimal("250"),
            stock_quantity=2,
        )
        self.serial = ProductSerial.objects.create(
            product=self.product,
            product_variant=self.variant,
            serial_number="SN-ABC-001",
        )
        self.user = User.objects.create_user(
            "label-user", "label@example.com", "pw", is_staff=True
        )
        self.client.force_login(self.user)

    def test_product_labels_render_variant_sku(self):
        response = self.client.get(reverse("staff_product_labels", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LP-100-USB")
        self.assertContains(response, "Print labels")

    def test_serial_label_renders_serial_number(self):
        response = self.client.get(reverse("staff_serial_labels", args=[self.serial.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SN-ABC-001")

    def test_stocktake_labels_render_take_and_line(self):
        take = StockTake.objects.create(name="June count", created_by=self.user)
        StockTakeLine.objects.create(
            take=take,
            product=self.product,
            product_variant=self.variant,
            system_quantity=2,
            counted_quantity=2,
        )
        response = self.client.get(reverse("staff_stocktake_labels", args=[take.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, take.reference)
        self.assertContains(response, "LP-100-USB")


class WarrantyCenterViewTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Warranty", slug="warranty")
        self.customer = Customer.objects.create(
            name="Ada Client",
            email="ada@example.com",
            phone="+254700000001",
        )
        self.product = Product.objects.create(
            category=self.cat,
            name="Business laptop",
            slug="business-laptop",
            sku="BL-14",
            price=Decimal("1200"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=1,
        )
        self.serial = ProductSerial.objects.create(
            product=self.product,
            serial_number="SN-RMA-900",
            imei="IMEI-RMA-900",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.customer,
            sold_at="2026-01-15",
            warranty_months=12,
        )
        self.job = JobCard.objects.create(
            customer=self.customer,
            title="Intermittent display fault",
            status=JobCard.STATUS_DIAGNOSING,
            serial_number="SN-RMA-900",
            device_make="Lenovo",
            device_model="T14",
        )
        self.ticket = SupportTicket.objects.create(
            customer=self.customer,
            subject="Warranty claim for display",
            description="Customer reports a display issue.",
            category=SupportTicket.CATEGORY_WARRANTY,
            related_serial=self.serial,
        )
        self.document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-RMA-900",
            customer=self.customer,
        )
        CommercialLine.objects.create(
            document=self.document,
            product=self.product,
            description="Business laptop",
            sku="BL-14",
            serial_number="SN-RMA-900",
            warranty="12 months",
            quantity=1,
            unit_price=Decimal("1200"),
        )
        self.user = User.objects.create_user(
            "warranty-user", "warranty@example.com", "pw", is_staff=True
        )

    def test_lookup_connects_serial_ticket_job_and_document_line(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("staff_warranty_center"), {"q": "SN-RMA-900"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business laptop")
        self.assertContains(response, "Under warranty")
        self.assertContains(response, self.ticket.reference)
        self.assertContains(response, "Intermittent display fault")
        self.assertContains(response, "INV-RMA-900")
        self.assertContains(response, "12 months")


class StockTakeTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="C-stk", slug="c-stk")
        self.product = Product.objects.create(
            category=self.cat,
            name="Mouse",
            slug="mouse-stk",
            price=Decimal("15"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=20,
        )
        self.user = User.objects.create_user("stk", "stk@example.com", "pw", is_staff=True)

    def test_post_applies_variance(self):
        take = StockTake.objects.create(name="Test count", created_by=self.user)
        StockTakeLine.objects.create(
            take=take,
            product=self.product,
            system_quantity=20,
            counted_quantity=18,
        )
        posted = take.post(actor=self.user)
        self.assertEqual(posted, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 18)
        self.assertEqual(take.status, StockTake.STATUS_POSTED)
        self.assertTrue(
            StockAdjustment.objects.filter(
                product=self.product, reason=StockAdjustment.REASON_COUNT
            ).exists()
        )

    def test_zero_variance_creates_no_adjustment(self):
        take = StockTake.objects.create(name="No diff", created_by=self.user)
        StockTakeLine.objects.create(
            take=take,
            product=self.product,
            system_quantity=20,
            counted_quantity=20,
        )
        take.post(actor=self.user)
        self.assertFalse(
            StockAdjustment.objects.filter(
                product=self.product, reason=StockAdjustment.REASON_COUNT
            ).exists()
        )


class AutoReturnOnCancelTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="C-ret", slug="c-ret")
        self.product = Product.objects.create(
            category=self.cat,
            name="Battery",
            slug="battery-ret",
            price=Decimal("50"),
            kind=Product.KIND_PHYSICAL,
            stock_quantity=10,
        )
        self.customer = Customer.objects.create(name="W", email="w-ret@example.com")
        self.user = User.objects.create_user("ret", "ret@example.com", "pw", is_staff=True)

    def test_cancel_restores_consumed_parts(self):
        job = JobCard.objects.create(
            customer=self.customer,
            title="Swap battery",
            status=JobCard.STATUS_INTAKE,
        )
        adj = StockAdjustment.objects.create(
            product=self.product,
            quantity_delta=-3,
            reason=StockAdjustment.REASON_JOB,
            job=job,
            created_by=self.user,
        )
        adj.apply()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        job.status = JobCard.STATUS_CANCELLED
        job._status_actor = self.user
        job.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertEqual(
            StockAdjustment.objects.filter(
                job=job, reason=StockAdjustment.REASON_RETURN
            ).count(),
            1,
        )
