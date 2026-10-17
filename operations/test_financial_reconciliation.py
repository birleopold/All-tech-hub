"""Phase 6 finance approval and job to invoice exception paths."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument, CommercialLine
from crm.models import Customer
from operations.job_financials import job_financial_reconciliation
from operations.models import JobCard, JobExpense


class JobInvoiceReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(
            name="Invoice owner", email="job-owner@example.com"
        )
        cls.other = Customer.objects.create(
            name="Other invoice owner", email="other-owner@example.com"
        )
        cls.doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-JOB-MARGIN-1",
            customer=cls.customer,
            status=CommercialDocument.STATUS_ISSUED,
            subtotal=Decimal("100000.00"),
            total=Decimal("100000.00"),
        )
        CommercialLine.objects.create(
            document=cls.doc, description="Network installation",
            source_type=CommercialLine.SOURCE_SERVICE,
            quantity=1, unit_price=Decimal("100000"),
            unit_cost=Decimal("40000"),
        )
        cls.job = JobCard.objects.create(
            customer=cls.customer, title="Site WiFi deployment",
            related_invoice=cls.doc,
        )
        JobExpense.objects.create(
            job=cls.job, category=JobExpense.CATEGORY_TRANSPORT,
            description="Actual travel", reference="P6-TRAVEL-1",
            amount=Decimal("10000"),
        )

    def test_issued_invoice_reports_values_without_double_counting_cost(self):
        result = job_financial_reconciliation(self.job)
        self.assertEqual(result["status"], "Comparison available")
        self.assertEqual(result["recorded_direct_cost"], Decimal("10000"))
        self.assertEqual(result["invoice_income"], Decimal("100000"))
        self.assertEqual(result["invoice_business_cost"], Decimal("40000"))
        self.assertEqual(result["invoice_contribution"], Decimal("60000"))
        self.assertIn("separately", result["note"])

    def test_shared_invoice_never_allocates_revenue_to_each_job(self):
        JobCard.objects.create(
            customer=self.customer,
            title="Other installation on same invoice",
            related_invoice=self.doc,
        )
        result = job_financial_reconciliation(self.job)
        self.assertEqual(result["status"], "Shared invoice")
        self.assertIsNone(result["invoice_income"])
        self.assertIsNone(result["invoice_contribution"])

    def test_cross_customer_invoice_rejected_by_job_validation(self):
        other_invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-OTHER-CUSTOMER",
            customer=self.other,
        )
        self.job.related_invoice = other_invoice
        with self.assertRaises(ValidationError):
            self.job.full_clean()


class ApprovalBoundaryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            "standard-sales-approver-test", password="pw", is_staff=True
        )
        self.approver = User.objects.create_user(
            "manager-approver-test", password="pw", is_staff=True
        )
        self.approver.user_permissions.add(Permission.objects.get(
            content_type__app_label="billing",
            codename="approve_high_value_document",
        ))
        customer = Customer.objects.create(
            name="Approval client", email="approval-client@example.com"
        )
        self.quote = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE,
            number="QUO-P6-APPROVAL-1", customer=customer,
            quote_requires_internal_approval=True,
        )

    def test_ordinary_sales_staff_cannot_approve_quotation(self):
        self.client.force_login(self.staff)
        url = reverse("staff_document_quote_approve", args=[self.quote.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.quote.refresh_from_db()
        self.assertFalse(self.quote.quote_internally_approved)

    def test_authorised_manager_approves_only_once(self):
        self.client.force_login(self.approver)
        url = reverse("staff_document_quote_approve", args=[self.quote.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.quote_internally_approved)
        approved_at = self.quote.quote_approved_at
        self.assertIsNotNone(approved_at)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.quote_approved_at, approved_at)
