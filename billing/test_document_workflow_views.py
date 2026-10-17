from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument


class CommercialDocumentWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="document-workflow-user",
            password="pw",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def _receipt_payload(self, **overrides):
        payload = {
            "doc_type": CommercialDocument.TYPE_RECEIPT,
            "customer": "",
            "customer_name": "",
            "customer_company": "",
            "customer_email": "",
            "customer_phone": "0770000000",
            "customer_tax_reference": "",
            "customer_address": "",
            "title": "",
            "issue_date": timezone.localdate().isoformat(),
            "due_date": "",
            "status": CommercialDocument.STATUS_ISSUED,
            "notes": "",
            "terms": "",
            "pricing_mode": CommercialDocument.PRICING_EXCLUSIVE,
            "tax_rate": "0",
            "discount_type": CommercialDocument.DISCOUNT_PERCENT,
            "discount_value": "0",
            "shipping_amount": "0",
            "other_charges_label": "",
            "other_charges": "0",
            "withholding_tax_rate": "0",
            "amount_tendered": "100000",
            "receipt_payment_method": "cash",
            "receipt_payment_reference": "",
            "salesperson": "",
            "location": "",
            "vehicle_reference": "",
            "contact_reference": "",
            "order": "",
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": "",
            "lines-0-product_variant": "",
            "lines-0-source_type": "custom",
            "lines-0-description": "Counter sale item",
            "lines-0-quantity": "1",
            "lines-0-unit_price": "100000",
            "lines-0-unit_cost": "0",
            "lines-0-discount_type": "percent",
            "lines-0-discount_value": "0",
            "lines-0-tax_rate": "0",
            "lines-0-sku": "",
            "lines-0-serial_number": "",
            "lines-0-warranty": "",
            "lines-0-line_note": "",
            "lines-0-section": "",
            "lines-0-sort_order": "0",
            "lines-0-supplier_name": "",
            "lines-0-source_reference": "",
            "lines-1-product": "",
            "lines-1-product_variant": "",
            "lines-1-source_type": "custom",
            "lines-1-description": "",
            "lines-1-quantity": "",
            "lines-1-unit_price": "",
            "lines-1-unit_cost": "",
            "lines-1-discount_type": "",
            "lines-1-discount_value": "",
            "lines-1-tax_rate": "",
            "lines-1-sku": "",
            "lines-1-serial_number": "",
            "lines-1-warranty": "",
            "lines-1-line_note": "",
            "lines-1-section": "",
            "lines-1-sort_order": "1",
            "lines-1-supplier_name": "",
            "lines-1-source_reference": "",
        }
        payload.update(overrides)
        return payload

    def test_create_and_download_pdf_saves_blank_walk_in_receipt(self):
        response = self.client.post(
            reverse("staff_document_create"),
            self._receipt_payload(save_action="pdf"),
        )

        self.assertEqual(
            response.status_code, 302,
            getattr(getattr(response, "context", None), "errors", None)
            or response.content.decode("utf-8", errors="replace")[:800],
        )
        document = CommercialDocument.objects.get()
        self.assertEqual(document.customer_name, "Walk-in customer")
        self.assertEqual(document.doc_type, CommercialDocument.TYPE_RECEIPT)
        self.assertRedirects(
            response,
            reverse("staff_document_pdf", args=[document.pk]) + "?download=1",
            fetch_redirect_response=False,
        )

    def test_receipt_list_search_finds_walk_in_phone(self):
        self.client.post(
            reverse("staff_document_create"),
            self._receipt_payload(save_action="view"),
        )

        response = self.client.get(reverse("staff_documents") + "?q=0770000000")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Walk-in customer")
        self.assertContains(response, "Download PDF")
