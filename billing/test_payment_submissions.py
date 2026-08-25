from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from commerce.models import Order
from crm.models import Customer
from reliability.models import PaymentAttempt

from billing.models import CommercialDocument, DocumentPayment, PaymentSubmission
from billing.payment_submissions import (
    reject_payment_submission,
    submit_payment_confirmation,
    verify_payment_submission,
)


class ManualPaymentSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="payment-reviewer", password="test-password", is_staff=True,
            is_superuser=True,
        )

    def setUp(self):
        self.document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-MANUAL-001",
            customer_name="Manual payment customer",
            customer_email="customer@example.com",
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("100000.00"),
        )
        self.document.ensure_payment_request_token()
        self.document.save(update_fields=["payment_request_token", "updated_at"])

    def submit(self, reference="MOMO-123", amount="40000.00"):
        return submit_payment_confirmation(
            document=self.document,
            amount=amount,
            method="Mobile Money",
            reference=reference,
            payer_name="Manual payment customer",
        )

    def test_public_submission_creates_pending_record_without_marking_paid(self):
        response = self.client.post(
            reverse("payment_request_portal", kwargs={
                "token": self.document.payment_request_token
            }),
            {
                "amount": "40000",
                "method": "mobile_money",
                "reference": "momo-public-1",
                "payer_name": "Customer",
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = PaymentSubmission.objects.get()
        self.assertEqual(submission.status, PaymentSubmission.STATUS_PENDING)
        self.assertEqual(submission.reference, "MOMO-PUBLIC-1")
        self.document.refresh_from_db()
        self.assertEqual(self.document.amount_paid, Decimal("0"))
        self.assertEqual(DocumentPayment.objects.count(), 0)

    def test_verification_records_and_reconciles_document_payment(self):
        submission, created = self.submit()
        self.assertTrue(created)
        payment = verify_payment_submission(submission, actor=self.staff)
        self.document.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("40000.00"))
        self.assertTrue(payment.reconciled)
        self.assertEqual(self.document.amount_paid, Decimal("40000.00"))
        self.assertEqual(self.document.status, CommercialDocument.STATUS_PARTIALLY_PAID)
        self.assertEqual(submission.status, PaymentSubmission.STATUS_VERIFIED)

    def test_full_payment_marks_document_paid(self):
        submission, _ = self.submit(amount="100000")
        verify_payment_submission(submission, actor=self.staff)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, CommercialDocument.STATUS_PAID)

    def test_duplicate_reference_is_idempotent(self):
        first, created = self.submit()
        second, created_again = self.submit(reference="momo-123")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentSubmission.objects.count(), 1)

    def test_reference_cannot_be_reused_for_different_amount(self):
        self.submit()
        with self.assertRaises(ValidationError):
            self.submit(amount="30000")

    def test_overpayment_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.submit(amount="100001")

    def test_rejection_never_records_payment(self):
        submission, _ = self.submit()
        reject_payment_submission(submission, actor=self.staff, reason="Not received")
        submission.refresh_from_db()
        self.assertEqual(submission.status, PaymentSubmission.STATUS_REJECTED)
        self.assertEqual(submission.review_note, "Not received")
        self.assertEqual(DocumentPayment.objects.count(), 0)

    def test_finance_queue_shows_pending_submission(self):
        self.submit(reference="QUEUE-001")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_payment_reconciliation"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QUEUE-001")
        self.assertContains(response, "Verify &amp; apply", html=False)

    def test_order_linked_payment_tracks_reliability_attempt(self):
        customer = Customer.objects.create(
            name="Order customer", email="order@example.com"
        )
        order = Order.objects.create(
            reference="ORD-MANUAL-001",
            customer=customer,
            contact_name=customer.name,
            contact_email=customer.email,
            subtotal=Decimal("100000.00"),
            total=Decimal("100000.00"),
        )
        self.document.order = order
        self.document.customer = customer
        self.document.save(update_fields=["order", "customer", "updated_at"])

        submission, _ = self.submit(reference="ORDER-MOMO-1")
        self.assertEqual(
            submission.payment_attempt.status, PaymentAttempt.STATUS_PENDING
        )
        verify_payment_submission(submission, actor=self.staff)
        submission.payment_attempt.refresh_from_db()
        self.assertEqual(
            submission.payment_attempt.status, PaymentAttempt.STATUS_PAID
        )

    def test_staff_approval_endpoint_applies_payment(self):
        submission, _ = self.submit()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("staff_payment_submission_approve", args=[submission.pk])
        )
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, PaymentSubmission.STATUS_VERIFIED)
