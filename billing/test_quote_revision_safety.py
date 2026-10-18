"""Issued quotation versions require renewed approval after any revision."""
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from billing.models import CommercialDocument, CommercialLine, DocumentPayment
from crm.models import Customer


@override_settings(SECURE_SSL_REDIRECT=False)
class IssuedQuotationRevisionSafetyTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser(
            username="quote-revision-manager", email="revision@example.com", password="pw"
        )
        self.client.force_login(self.staff)
        self.customer = Customer.objects.create(
            name="Revision buyer", email="revision-buyer@example.com"
        )
        self.quote = CommercialDocument.objects.create(
            number="QUO-REVISION-001",
            customer=self.customer, doc_type=CommercialDocument.TYPE_QUOTE,
            status=CommercialDocument.STATUS_ISSUED,
            locked_at=timezone.now(), locked_by=self.staff,
            quote_requires_internal_approval=True,
            quote_internally_approved=True,
            quote_approved_by=self.staff,
            quote_approved_at=timezone.now(),
            quote_requires_customer_acceptance=True,
            quote_customer_token=uuid4(),
            quote_customer_accepted=True,
            quote_customer_signature_name="Revision buyer",
            quote_customer_responded_at=timezone.now(),
        )
        CommercialLine.objects.create(
            document=self.quote, description="Original specification",
            quantity=1, unit_price=250000,
        )

    def revise(self, doc):
        return self.client.post(
            reverse("staff_document_revise", args=[doc.pk]),
            {"reason": "Specifications changed after customer discussion"},
        )

    def test_new_quotation_version_revokes_prior_approval_and_private_link(self):
        previous_token = self.quote.quote_customer_token
        response = self.revise(self.quote)
        self.assertEqual(response.status_code, 302)
        self.quote.refresh_from_db()
        self.assertFalse(self.quote.is_locked)
        self.assertEqual(self.quote.status, CommercialDocument.STATUS_DRAFT)
        self.assertFalse(self.quote.quote_internally_approved)
        self.assertIsNone(self.quote.quote_approved_at)
        self.assertIsNone(self.quote.quote_approved_by)
        self.assertIsNone(self.quote.quote_customer_accepted)
        self.assertIsNone(self.quote.quote_customer_responded_at)
        self.assertEqual(self.quote.quote_customer_signature_name, "")
        self.assertNotEqual(previous_token, self.quote.quote_customer_token)
        original = self.quote.revisions.get()
        self.assertEqual(original.snapshot["quote_acceptance"]["customer_accepted"], True)
        self.assertEqual(original.snapshot["quote_acceptance"]["customer_signature_name"], "Revision buyer")
        self.assertEqual(original.snapshot["lines"][0]["description"], "Original specification")
        self.assertEqual(
            self.client.get(reverse("quote_customer_portal", args=[previous_token])).status_code,
            404,
        )

    def test_repeated_revision_request_does_not_create_another_snapshot(self):
        self.revise(self.quote)
        again = self.revise(self.quote)
        self.assertEqual(again.status_code, 302)
        self.assertEqual(self.quote.revisions.count(), 1)

    def test_paid_cancelled_or_inventory_posted_records_cannot_be_unlocked(self):
        statuses = [
            (CommercialDocument.STATUS_PAID, False),
            (CommercialDocument.STATUS_CANCELLED, False),
            (CommercialDocument.STATUS_ISSUED, True),
        ]
        for index, (status, posted) in enumerate(statuses):
            doc = CommercialDocument.objects.create(
                number=f"INV-REVISION-{index}",
                doc_type=CommercialDocument.TYPE_INVOICE,
                customer=self.customer, status=status,
                locked_at=timezone.now(), locked_by=self.staff,
                inventory_posted_at=timezone.now() if posted else None,
            )
            self.assertEqual(self.revise(doc).status_code, 302)
            doc.refresh_from_db()
            self.assertTrue(doc.is_locked)
            self.assertFalse(doc.revisions.exists())

    def test_document_with_payment_cannot_be_revised_even_when_issued(self):
        invoice = CommercialDocument.objects.create(
            number="INV-REVISION-PAID-ENTRY",
            doc_type=CommercialDocument.TYPE_INVOICE,
            customer=self.customer, status=CommercialDocument.STATUS_ISSUED,
            locked_at=timezone.now(), locked_by=self.staff,
        )
        DocumentPayment.objects.create(
            document=invoice, amount=1000,
            method=DocumentPayment.METHOD_CASH,
        )
        self.assertEqual(self.revise(invoice).status_code, 302)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_locked)
        self.assertFalse(invoice.revisions.exists())
