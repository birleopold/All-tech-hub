from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductSerial, ProductVariant
from core.models import AuditEvent
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
