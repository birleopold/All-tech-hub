from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from crm.models import Customer
from operations.models import JobCard, JobExpense


class FieldFinanceReportTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Field reporting customer", email="field-report@example.com"
        )
        self.job = JobCard.objects.create(
            customer=self.customer, title="Router installation"
        )
        self.expense = JobExpense.objects.create(
            job=self.job, category=JobExpense.CATEGORY_TRANSPORT,
            description="Actual installation transport", reference="TRANS-9",
            amount=Decimal("12500.00"),
        )
        self.finance = User.objects.create_user(
            "field-report-finance", password="pw", is_staff=True
        )
        self.operations = User.objects.create_user(
            "field-report-operations", password="pw", is_staff=True
        )
        self.finance.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="billing",
            codename="view_document_margin",
        ))
        self.finance.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="operations",
            codename="view_jobexpense",
        ))

    def test_finance_sees_recorded_cost_separately(self):
        self.client.force_login(self.finance)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recorded field-job expenses")
        self.assertContains(response, "TRANS-9", count=0)
        self.assertContains(response, self.job.number)
        self.assertEqual(
            response.context["recorded_job_expenses_30"]["total"],
            Decimal("12500.00"),
        )

    def test_nonfinance_sees_operations_without_expenses(self):
        self.client.force_login(self.operations)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations reports")
        self.assertNotContains(response, "Recorded field-job expenses")
        self.assertNotIn("recorded_job_expenses_30", response.context)
        for name in (
            "staff_export_margin_lines_csv",
            "staff_export_partner_payables_csv",
            "staff_export_documents_csv",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(reverse(name)).status_code, 404
                )

    def test_margin_permission_without_job_expense_permission_hides_costs(self):
        margin_only = User.objects.create_user(
            "margin-only", password="pw", is_staff=True
        )
        margin_only.user_permissions.add(Permission.objects.get(
            content_type__app_label="billing",
            codename="view_document_margin",
        ))
        self.client.force_login(margin_only)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Recorded field-job expenses")
        self.assertNotIn("recorded_job_expenses_30", response.context)
