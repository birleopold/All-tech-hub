"""Financial access and invoice-independent cost records for field jobs."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AuditEvent
from crm.models import Customer
from operations.models import JobCard, JobExpense


@override_settings(SECURE_SSL_REDIRECT=False)
class JobExpenseLedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.finance = User.objects.create_user(
            "field-finance", password="pw", is_staff=True
        )
        cls.tech = User.objects.create_user(
            "field-technician", password="pw", is_staff=True
        )
        cls.finance.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="operations",
            codename__in=["add_jobexpense", "view_jobexpense"],
        ))
        cls.customer = Customer.objects.create(
            name="Expense customer", email="expense.customer@example.com"
        )
        cls.job = JobCard.objects.create(
            customer=cls.customer, title="Office network installation"
        )

    def setUp(self):
        self.client.force_login(self.finance)

    def _payload(self, ref="TRAVEL-047", amount="15000.50"):
        return {
            "category": JobExpense.CATEGORY_TRANSPORT,
            "description": "Installer transport to the customer",
            "reference": ref, "amount": amount,
        }

    def test_record_cost_once_without_a_customer_payment_or_invoice(self):
        url = reverse("staff_job_expense", args=[self.job.pk])
        response = self.client.post(url, self._payload())
        self.assertEqual(response.status_code, 302)
        saved = JobExpense.objects.get(job=self.job)
        self.assertEqual(saved.amount, Decimal("15000.50"))
        self.assertEqual(saved.recorded_by_id, self.finance.pk)
        self.assertTrue(AuditEvent.objects.filter(
            verb="job.expense_recorded", target_id=saved.pk
        ).exists())
        detail = self.client.get(
            reverse("staff_job_detail", args=[self.job.pk])
        )
        self.assertContains(detail, "Direct job expenses")
        self.assertContains(detail, "15000.50")
        self.assertEqual(
            detail.context["recorded_direct_cost"], Decimal("15000.50")
        )

    def test_duplicate_source_reference_never_double_counts(self):
        url = reverse("staff_job_expense", args=[self.job.pk])
        self.client.post(url, self._payload())
        second = self.client.post(url, self._payload(amount="35000.50"))
        self.assertEqual(second.status_code, 302)
        self.assertEqual(JobExpense.objects.filter(job=self.job).count(), 1)

    def test_invalid_or_zero_amount_is_rejected(self):
        response = self.client.post(
            reverse("staff_job_expense", args=[self.job.pk]),
            self._payload(ref="VOID", amount="0"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(JobExpense.objects.filter(job=self.job).exists())

    def test_technician_cannot_view_costs_or_post_expenses(self):
        JobExpense.objects.create(
            job=self.job, category=JobExpense.CATEGORY_PARTS,
            amount=Decimal("250000.00"), description="Purchased switch",
            reference="SWITCH-018", recorded_by=self.finance,
        )
        self.client.force_login(self.tech)
        response = self.client.get(
            reverse("staff_job_detail", args=[self.job.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Direct job expenses")
        self.assertNotContains(response, "250000")
        denied = self.client.post(
            reverse("staff_job_expense", args=[self.job.pk]),
            self._payload(),
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(JobExpense.objects.filter(job=self.job).count(), 1)
