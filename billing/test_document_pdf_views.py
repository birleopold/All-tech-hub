from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument, CommercialLine, allocate_document_number


class StaffDocumentPdfResponseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pdf-counter-user", password="pw", is_staff=True)
        self.client.force_login(self.user)
        self.document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_RECEIPT,
            number=allocate_document_number("REC"),
            customer_name="Walk-in customer",
            status=CommercialDocument.STATUS_PAID,
            issue_date=timezone.localdate(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
            amount_tendered=Decimal("100.00"),
            receipt_payment_method="cash",
        )
        CommercialLine.objects.create(
            document=self.document,
            description="Counter sale item",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

    def test_document_pdf_downloads_by_default(self):
        response = self.client.get(reverse("staff_document_pdf", args=[self.document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_document_pdf_can_still_open_inline_when_requested(self):
        response = self.client.get(reverse("staff_document_pdf", args=[self.document.pk]) + "?inline=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("inline", response["Content-Disposition"])

    def test_download_parameter_overrides_inline_preview(self):
        response = self.client.get(reverse("staff_document_pdf", args=[self.document.pk]) + "?inline=1&download=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
