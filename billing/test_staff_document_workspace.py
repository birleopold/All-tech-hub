from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument
from crm.models import Customer


class StaffDocumentWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("document-staff", password="pw", is_staff=True)
        cls.customer = Customer.objects.create(
            name="Document Customer",
            email="documents@example.com",
        )
        CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE,
            number="QUO-WORKSPACE-1",
            customer=cls.customer,
            customer_name=cls.customer.name,
            status=CommercialDocument.STATUS_DRAFT,
            total=Decimal("100000"),
        )
        CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-WORKSPACE-1",
            customer=cls.customer,
            customer_name=cls.customer.name,
            status=CommercialDocument.STATUS_PAID,
            total=Decimal("200000"),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_document_workspace_renders_summary_and_register(self):
        response = self.client.get(reverse("staff_documents"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document_stats"]["total"], 2)
        self.assertEqual(response.context["document_stats"]["drafts"], 1)
        self.assertEqual(response.context["document_stats"]["paid"], 1)
        self.assertContains(response, "Commercial documents")
        self.assertContains(response, "Document register")
        self.assertContains(response, "staff-status-pill--neutral")
        self.assertContains(response, "staff-status-pill--success")

    def test_document_workspace_filters_by_type_and_search(self):
        invoice_response = self.client.get(
            reverse("staff_documents"), {"type": CommercialDocument.TYPE_INVOICE}
        )
        search_response = self.client.get(reverse("staff_documents"), {"q": "QUO-WORKSPACE"})

        self.assertEqual(invoice_response.context["paginator"].count, 1)
        self.assertContains(invoice_response, "INV-WORKSPACE-1")
        self.assertNotContains(invoice_response, "QUO-WORKSPACE-1")
        self.assertEqual(search_response.context["paginator"].count, 1)
        self.assertContains(search_response, "QUO-WORKSPACE-1")

    def test_document_composer_keeps_existing_line_and_save_controls(self):
        response = self.client.get(reverse("staff_document_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staff_document_composer.css")
        self.assertContains(response, "Quick start")
        self.assertContains(response, "Document summary")
        self.assertContains(response, "Customer and items")
        self.assertContains(response, 'id="document-form"')
        self.assertContains(response, 'id="line-table"')
        self.assertContains(response, 'id="empty-line-template"')
        self.assertContains(response, 'id="id_lines-TOTAL_FORMS"')
        self.assertContains(response, 'id="primary-save-button"')
        self.assertContains(response, 'id="secondary-save-button"')

    def test_document_composer_styles_prevent_collapsed_line_item_columns(self):
        stylesheet = (
            Path(settings.BASE_DIR)
            / "static"
            / "css"
            / "staff_document_composer.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".document-lines-scroll", stylesheet)
        self.assertIn("overflow-x: auto", stylesheet)
        self.assertIn("min-width: 1030px", stylesheet)
        self.assertIn("white-space: nowrap", stylesheet)
