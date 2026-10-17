from decimal import Decimal
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from billing.models import CommercialDocument, DocumentPayment, PaymentRefund
from crm.models import Customer


class FinanceControlTests(TestCase):
    def setUp(self):
        self.finance = User.objects.create_user(
            "finance-authorised", password="pw", is_staff=True
        )
        self.other = User.objects.create_user(
            "other-staff-finance", password="pw", is_staff=True
        )
        self.finance.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="billing",
            codename__in=["add_paymentrefund", "change_documentpayment"],
        ))
        customer = Customer.objects.create(
            name="Payment customer", email="payment-customer@example.com"
        )
        self.document = CommercialDocument.objects.create(
            customer=customer, doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-REFUND-REGRESSION", total=Decimal("100"),
            amount_paid=Decimal("100"), status=CommercialDocument.STATUS_PAID,
        )
        self.payment = DocumentPayment.objects.create(
            document=self.document, amount=Decimal("100"),
            method=DocumentPayment.METHOD_CASH,
        )

    def refund(self, reference="RF-JOB-1"):
        return self.client.post(
            reverse("staff_payment_refund", args=[self.payment.pk]),
            {"amount": "25", "reason": "Customer return", "reference": reference},
        )

    def test_staff_without_finance_permission_cannot_change_payments(self):
        self.client.force_login(self.other)
        self.assertEqual(self.refund().status_code, 404)
        self.assertEqual(self.client.post(reverse(
            "staff_payment_reconcile", args=[self.payment.pk]
        )).status_code, 404)
        self.assertFalse(PaymentRefund.objects.exists())

    def test_refund_reference_can_be_recorded_once(self):
        self.client.force_login(self.finance)
        self.assertEqual(self.refund().status_code, 302)
        self.assertEqual(self.refund().status_code, 302)
        self.assertEqual(PaymentRefund.objects.count(), 1)
        self.assertTrue(PaymentRefund.objects.get().idempotency_key)
        self.document.refresh_from_db()
        self.assertEqual(self.document.amount_paid, Decimal("75"))

    def test_empty_refund_reference_cannot_create_record(self):
        self.client.force_login(self.finance)
        self.assertEqual(self.refund(reference="").status_code, 302)
        self.assertFalse(PaymentRefund.objects.exists())

    def test_reconcile_twice_does_not_change_timestamp(self):
        self.client.force_login(self.finance)
        url = reverse("staff_payment_reconcile", args=[self.payment.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        first = DocumentPayment.objects.get(pk=self.payment.pk).reconciled_at
        self.assertIsNotNone(first)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(
            DocumentPayment.objects.get(pk=self.payment.pk).reconciled_at, first
        )
