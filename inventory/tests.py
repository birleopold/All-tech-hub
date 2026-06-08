from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from core.models import AuditEvent
from crm.models import Customer
from inventory.forms import JobStockUseForm
from inventory.models import StockAdjustment, StockTake, StockTakeLine
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
        self.assertEqual(adj.quantity_delta, -2)
        self.assertEqual(adj.reason, StockAdjustment.REASON_JOB)
        self.assertTrue(
            AuditEvent.objects.filter(verb="inventory.job_part_use").exists()
        )


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
