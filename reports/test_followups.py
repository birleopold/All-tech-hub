from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductSerial
from commerce.models import Order
from crm.models import Customer
from loyalty.models import CustomerMarketingPreference
from reports.followups import (
    close_followup,
    customer_outreach_allowed,
    open_followup_whatsapp,
    refresh_retention_followups,
    send_followup_email,
)
from reports.models import CustomerFollowUp


class CustomerRetentionFollowUpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(
            username="retention-followup-manager",
            password="strong-test-password",
            email="manager@example.com",
        )

    def setUp(self):
        category = Category.objects.create(name="Follow-up laptops", slug="follow-up-laptops")
        self.product = Product.objects.create(
            category=category,
            name="Warranty laptop",
            slug="follow-up-warranty-laptop",
            price=Decimal("1200000.00"),
            stock_quantity=5,
        )
        self.warranty_customer = Customer.objects.create(
            name="Warranty customer",
            email="warranty@example.com",
            phone="0700123456",
        )
        self.dormant_customer = Customer.objects.create(
            name="Dormant customer",
            email="dormant@example.com",
            phone="0700654321",
        )
        expiry_target = timezone.localdate() + timedelta(days=15)
        previous_month = expiry_target.month - 1
        year = expiry_target.year
        if previous_month == 0:
            previous_month = 12
            year -= 1
        sold_on = date(year, previous_month, min(expiry_target.day, 28))
        self.serial = ProductSerial.objects.create(
            product=self.product,
            serial_number="FOLLOWUP-SERIAL-001",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.warranty_customer,
            sold_at=sold_on,
            warranty_months=1,
        )
        self.order = Order.objects.create(
            reference="ORD-DORMANT-FOLLOWUP",
            customer=self.dormant_customer,
            contact_name=self.dormant_customer.name,
            contact_email=self.dormant_customer.email,
            total=Decimal("400000.00"),
            status=Order.STATUS_FULFILLED,
        )
        Order.objects.filter(pk=self.order.pk).update(
            placed_at=timezone.now() - timedelta(days=120)
        )

    def test_refresh_creates_warranty_and_dormant_customer_tasks(self):
        result = refresh_retention_followups(limit=20)
        self.assertEqual(result["warranty_created"], 1)
        self.assertEqual(result["dormant_created"], 1)
        self.assertEqual(CustomerFollowUp.objects.count(), 2)

    def test_refresh_is_idempotent(self):
        refresh_retention_followups(limit=20)
        result = refresh_retention_followups(limit=20)
        self.assertEqual(result["warranty_created"], 0)
        self.assertEqual(result["dormant_created"], 0)
        self.assertEqual(CustomerFollowUp.objects.count(), 2)

    def test_dry_run_does_not_create_tasks(self):
        result = refresh_retention_followups(limit=20, dry_run=True)
        self.assertEqual(result["warranty_created"], 1)
        self.assertEqual(result["dormant_created"], 1)
        self.assertEqual(CustomerFollowUp.objects.count(), 0)

    def test_warranty_reminder_is_transactional_without_marketing_consent(self):
        refresh_retention_followups()
        task = CustomerFollowUp.objects.get(
            follow_up_type=CustomerFollowUp.TYPE_WARRANTY_EXPIRY
        )
        log = send_followup_email(task, actor=self.staff)
        task.refresh_from_db()
        self.assertEqual(log.category, "transactional")
        self.assertEqual(task.status, CustomerFollowUp.STATUS_IN_PROGRESS)
        self.assertTrue(any("Warranty reminder" in item.subject for item in mail.outbox))

    def test_dormant_email_requires_explicit_marketing_consent(self):
        refresh_retention_followups()
        task = CustomerFollowUp.objects.get(
            follow_up_type=CustomerFollowUp.TYPE_DORMANT_CUSTOMER
        )
        self.assertFalse(customer_outreach_allowed(task, "email"))
        with self.assertRaises(ValidationError):
            send_followup_email(task, actor=self.staff)

    def test_consented_dormant_email_includes_unsubscribe_link(self):
        CustomerMarketingPreference.objects.create(
            customer=self.dormant_customer,
            email_marketing=True,
            product_updates=True,
        )
        refresh_retention_followups()
        task = CustomerFollowUp.objects.get(
            follow_up_type=CustomerFollowUp.TYPE_DORMANT_CUSTOMER
        )
        log = send_followup_email(task, actor=self.staff)
        self.assertEqual(log.category, "marketing")
        self.assertIn("unsubscribe", log.body)

    def test_whatsapp_followup_formats_ugandan_numbers(self):
        refresh_retention_followups()
        task = CustomerFollowUp.objects.get(
            follow_up_type=CustomerFollowUp.TYPE_WARRANTY_EXPIRY
        )
        url = open_followup_whatsapp(task, actor=self.staff)
        self.assertTrue(url.startswith("https://wa.me/256700123456?text="))

    def test_closing_followup_preserves_audit_and_prevents_second_close(self):
        refresh_retention_followups()
        task = CustomerFollowUp.objects.first()
        close_followup(task, actor=self.staff, note="Customer reached by phone")
        task.refresh_from_db()
        self.assertEqual(task.status, CustomerFollowUp.STATUS_COMPLETED)
        self.assertEqual(task.note, "Customer reached by phone")
        with self.assertRaises(ValidationError):
            close_followup(task, actor=self.staff)

    def test_dashboard_renders_actionable_followup_queue(self):
        refresh_retention_followups()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_retention_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer care queue")
        self.assertContains(response, "Warranty customer")
        self.assertContains(response, "Dormant customer")

    def test_manual_refresh_management_command_creates_tasks(self):
        call_command("refresh_customer_followups", limit=20)
        self.assertEqual(CustomerFollowUp.objects.count(), 2)

    def test_customer_followup_close_endpoint(self):
        refresh_retention_followups()
        task = CustomerFollowUp.objects.first()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("staff_retention_followup_close", args=[task.pk]),
            {"action": "complete", "note": "Customer happy"},
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, CustomerFollowUp.STATUS_COMPLETED)
