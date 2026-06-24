from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import (
    AccountPayment,
    CommercialDocument,
    CommercialLine,
    CustomerCredit,
    DocumentPayment,
    DocumentRevision,
    DocumentTemplate,
    PaymentAllocation,
    PaymentRefund,
    allocate_document_number,
)
from billing.pdf import render_commercial_pdf
from catalog.models import Category, Product, ProductVariant
from core.models import ContactMessage
from crm.models import Customer


class CommercialLineVariantTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Buyer", email="buyer@example.com")
        self.cat = Category.objects.create(name="C", slug="c-bill")
        self.p1 = Product.objects.create(
            category=self.cat,
            name="P1",
            slug="p1-bill",
            price=Decimal("10.00"),
            kind=Product.KIND_PHYSICAL,
        )
        self.p2 = Product.objects.create(
            category=self.cat,
            name="P2",
            slug="p2-bill",
            price=Decimal("20.00"),
            kind=Product.KIND_PHYSICAL,
        )
        self.v1 = ProductVariant.objects.create(
            product=self.p1,
            name="Opt",
            price=Decimal("12.00"),
            stock_quantity=1,
        )
        num = allocate_document_number("QUO")
        self.doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE,
            number=num,
            customer=self.customer,
            issue_date=timezone.localdate(),
        )

    def test_save_sets_product_from_variant(self):
        line = CommercialLine(
            document=self.doc,
            product=None,
            product_variant=self.v1,
            description="Line",
            quantity=Decimal("1"),
            unit_price=Decimal("12.00"),
        )
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.product_id, self.p1.pk)

    def test_clean_rejects_mismatched_product_and_variant(self):
        line = CommercialLine(
            document=self.doc,
            product=self.p2,
            product_variant=self.v1,
            description="Bad",
            quantity=Decimal("1"),
            unit_price=Decimal("1"),
        )
        with self.assertRaises(ValidationError):
            line.full_clean()


class CommercialDocumentEditorTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Document Buyer", email="documents@example.com"
        )
        self.user = User.objects.create_user(
            "document-editor", password="pw", is_staff=True
        )
        self.client.force_login(self.user)

    def document_payload(self, **overrides):
        payload = {
            "doc_type": CommercialDocument.TYPE_INVOICE,
            "customer": str(self.customer.pk),
            "customer_name": self.customer.name,
            "customer_company": "",
            "customer_email": self.customer.email,
            "customer_phone": "",
            "customer_tax_reference": "",
            "customer_address": "",
            "title": "Network installation",
            "issue_date": "2026-06-23",
            "due_date": "2026-07-07",
            "status": CommercialDocument.STATUS_DRAFT,
            "notes": "Schedule with the customer.",
            "terms": "Payment due within 14 days.",
            "tax_rate": "18.00",
            "order": "",
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": "",
            "lines-0-product_variant": "",
            "lines-0-description": "Router",
            "lines-0-quantity": "2",
            "lines-0-unit_price": "100.00",
            "lines-1-product": "",
            "lines-1-product_variant": "",
            "lines-1-description": "Configuration",
            "lines-1-quantity": "1",
            "lines-1-unit_price": "50.00",
            "save_action": "view",
        }
        payload.update(overrides)
        return payload

    def test_create_saves_header_lines_and_totals_atomically(self):
        response = self.client.post(
            reverse("staff_document_create"), self.document_payload()
        )
        document = CommercialDocument.objects.get()
        self.assertRedirects(
            response, reverse("staff_document_view", args=[document.pk])
        )
        self.assertEqual(document.lines.count(), 2)
        self.assertEqual(document.subtotal, Decimal("250.00"))
        self.assertEqual(document.tax_amount, Decimal("45.00"))
        self.assertEqual(document.total, Decimal("295.00"))
        self.assertEqual(document.created_by, self.user)
        self.assertEqual(document.customer_name, self.customer.name)

    def test_create_without_lines_does_not_leave_blank_document(self):
        payload = self.document_payload(
            **{
                "lines-0-description": "",
                "lines-0-quantity": "",
                "lines-0-unit_price": "",
                "lines-1-description": "",
                "lines-1-quantity": "",
                "lines-1-unit_price": "",
            }
        )
        response = self.client.post(reverse("staff_document_create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add at least one line item.")
        self.assertFalse(CommercialDocument.objects.exists())

    def test_invalid_due_date_is_rejected(self):
        response = self.client.post(
            reverse("staff_document_create"),
            self.document_payload(due_date="2026-06-01"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due date cannot be before the issue date.")
        self.assertFalse(CommercialDocument.objects.exists())

    def test_walk_in_document_needs_no_account_order_or_catalog_product(self):
        payload = self.document_payload(
            customer="",
            customer_name="Cash walk-in",
            customer_email="",
            order="",
            **{
                "lines-0-description": "Neighbour-supplied Wi-Fi extender",
                "lines-0-quantity": "1",
                "lines-0-unit_price": "85000.00",
                "lines-1-description": "Installation labour",
                "lines-1-quantity": "1",
                "lines-1-unit_price": "25000.00",
            },
        )
        response = self.client.post(reverse("staff_document_create"), payload)
        document = CommercialDocument.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(document.customer)
        self.assertIsNone(document.order)
        self.assertEqual(document.display_customer_name, "Cash walk-in")
        self.assertFalse(document.lines.exclude(product=None).exists())
        self.assertEqual(document.total, Decimal("129800.00"))

    def test_delivery_note_clears_due_date_but_keeps_staff_tax_rate(self):
        payload = self.document_payload(
            doc_type=CommercialDocument.TYPE_DELIVERY_NOTE,
            due_date="2026-07-07",
            tax_rate="18.00",
        )
        self.client.post(reverse("staff_document_create"), payload)
        document = CommercialDocument.objects.get()
        self.assertIsNone(document.due_date)
        self.assertEqual(document.tax_rate, Decimal("18.00"))
        self.assertEqual(document.tax_amount, Decimal("45.00"))

    def test_receipt_uses_receipt_status_choices(self):
        payload = self.document_payload(
            doc_type=CommercialDocument.TYPE_RECEIPT,
            status=CommercialDocument.STATUS_PAID,
        )
        self.client.post(reverse("staff_document_create"), payload)
        document = CommercialDocument.objects.get()
        self.assertEqual(document.status, CommercialDocument.STATUS_PAID)

    def test_linked_customer_details_are_a_historical_snapshot(self):
        self.client.post(reverse("staff_document_create"), self.document_payload())
        document = CommercialDocument.objects.get()
        self.customer.name = "Renamed after invoice"
        self.customer.email = "new-address@example.com"
        self.customer.save()
        document.refresh_from_db()
        self.assertEqual(document.display_customer_name, "Document Buyer")
        self.assertEqual(document.display_customer_email, "documents@example.com")

    def test_existing_customer_can_fill_snapshot_server_side(self):
        self.client.post(
            reverse("staff_document_create"),
            self.document_payload(customer_name="", customer_email=""),
        )
        document = CommercialDocument.objects.get()
        self.assertEqual(document.customer_name, self.customer.name)
        self.assertEqual(document.customer_email, self.customer.email)

    def test_walk_in_document_renders_pdf_without_crm_customer(self):
        self.client.post(
            reverse("staff_document_create"),
            self.document_payload(
                customer="",
                customer_name="PDF walk-in",
                customer_email="walkin@example.com",
            ),
        )
        document = CommercialDocument.objects.get()
        pdf = render_commercial_pdf(document)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_existing_document_can_be_saved_with_line_changes(self):
        document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number=allocate_document_number("INV"),
            customer=self.customer,
            issue_date=timezone.localdate(),
        )
        line = CommercialLine.objects.create(
            document=document,
            description="Old description",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
        )
        payload = self.document_payload(
            **{
                "issue_date": timezone.localdate().isoformat(),
                "due_date": "",
                "tax_rate": "0",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "1",
                "lines-0-id": str(line.pk),
                "lines-0-description": "Updated description",
                "lines-0-quantity": "2",
                "lines-0-unit_price": "15.00",
            }
        )
        response = self.client.post(
            reverse("staff_document_edit", args=[document.pk]), payload
        )
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(line.description, "Updated description")
        self.assertEqual(document.total, Decimal("30.00"))


class PaymentRequestLinkTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Paying Customer",
            email="payer@example.com",
            phone="+256700000000",
        )
        self.user = User.objects.create_user(
            "payment-link-user", password="pw", is_staff=True
        )
        self.client.force_login(self.user)
        self.document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number=allocate_document_number("INV"),
            customer=self.customer,
            customer_name=self.customer.name,
            customer_email=self.customer.email,
            customer_phone=self.customer.phone,
            status=CommercialDocument.STATUS_ISSUED,
            issue_date=timezone.localdate(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            amount_paid=Decimal("25.00"),
        )
        CommercialLine.objects.create(
            document=self.document,
            description="Router installation",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
        )

    def test_staff_can_generate_payment_request_link(self):
        response = self.client.post(
            reverse("staff_document_payment_link", args=[self.document.pk])
        )
        self.assertRedirects(
            response, reverse("staff_document_view", args=[self.document.pk])
        )
        self.document.refresh_from_db()
        self.assertIsNotNone(self.document.payment_request_token)

    def test_public_payment_request_page_renders(self):
        self.document.ensure_payment_request_token()
        self.document.save(update_fields=["payment_request_token"])
        self.client.logout()
        response = self.client.get(
            reverse("payment_request_portal", args=[self.document.payment_request_token])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Balance due")
        self.assertContains(response, "75.00")

    def test_payment_reference_submission_creates_contact_message(self):
        self.document.ensure_payment_request_token()
        self.document.save(update_fields=["payment_request_token"])
        self.client.logout()
        response = self.client.post(
            reverse("payment_request_portal", args=[self.document.payment_request_token]),
            {
                "payer_name": "Paying Customer",
                "payer_email": "payer@example.com",
                "payer_phone": "+256700000000",
                "method": "Mobile Money",
                "amount": "75.00",
                "reference": "MM123456",
            },
        )
        self.assertRedirects(
            response,
            reverse("payment_request_portal", args=[self.document.payment_request_token]),
        )
        message = ContactMessage.objects.get()
        self.assertEqual(
            message.subject, f"Payment confirmation for {self.document.number}"
        )
        self.assertIn("MM123456", message.message)


class QuoteInternalApprovalTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Buyer", email="buyer@example.com")
        self.user = User.objects.create_user("approver", "a@example.com", "secret", is_staff=True)
        num = allocate_document_number("QUO")
        self.doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE,
            number=num,
            customer=self.customer,
            quote_requires_internal_approval=True,
            quote_internally_approved=False,
        )

    def test_convert_to_invoice_blocked_until_approved(self):
        self.client.force_login(self.user)
        url = reverse("staff_document_to_invoice", args=[self.doc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertRedirects(response, reverse("staff_document_edit", args=[self.doc.pk]))
        before = CommercialDocument.objects.count()
        self.doc.refresh_from_db()
        self.doc.quote_internally_approved = True
        self.doc.save()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertGreater(CommercialDocument.objects.count(), before)


class QuoteCustomerAcceptanceTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Buyer", email="buyer@example.com")
        num = allocate_document_number("QUO")
        self.doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE,
            number=num,
            customer=self.customer,
            quote_requires_customer_acceptance=True,
        )
        self.doc.ensure_customer_quote_token()
        self.doc.save(update_fields=["quote_customer_token"])

    def test_customer_can_accept_quote(self):
        url = reverse("quote_customer_portal", kwargs={"token": self.doc.quote_customer_token})
        r = self.client.post(
            url,
            {"action": "accept", "signature_name": "Jane Buyer"},
        )
        self.assertEqual(r.status_code, 302)
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.quote_customer_accepted)
        self.assertEqual(self.doc.quote_customer_signature_name, "Jane Buyer")

    def test_convert_blocked_until_customer_accepts(self):
        user = User.objects.create_user("staff", "s@example.com", "pw", is_staff=True)
        self.client.force_login(user)
        url = reverse("staff_document_to_invoice", args=[self.doc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url)
        self.assertRedirects(r, reverse("staff_document_edit", args=[self.doc.pk]))

    def test_customer_can_decline_with_reason(self):
        url = reverse("quote_customer_portal", kwargs={"token": self.doc.quote_customer_token})
        r = self.client.post(
            url,
            {"action": "decline", "decline_reason": "Found cheaper option"},
        )
        self.assertEqual(r.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.quote_customer_accepted, False)
        self.assertEqual(self.doc.quote_customer_decline_reason, "Found cheaper option")


class PaymentRefundTests(TestCase):
    def test_refund_reverses_paid_amount_and_creates_credit_note(self):
        customer = Customer.objects.create(name="Refund", email="refund@example.com")
        user = User.objects.create_user("finance", password="pw", is_staff=True)
        doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number=allocate_document_number("INV"),
            customer=customer,
            status=CommercialDocument.STATUS_PAID,
            total=Decimal("100"),
            amount_paid=Decimal("100"),
        )
        payment = DocumentPayment.objects.create(
            document=doc,
            amount=Decimal("100"),
            method=DocumentPayment.METHOD_CASH,
            recorded_by=user,
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("staff_payment_refund", args=[payment.pk]),
            {"amount": "25.00", "reason": "Returned item", "reference": "RF1"},
        )
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.amount_paid, Decimal("75.00"))
        self.assertEqual(PaymentRefund.objects.count(), 1)
        self.assertTrue(
            CommercialDocument.objects.filter(
                doc_type=CommercialDocument.TYPE_CREDIT_NOTE,
                source_document=doc,
            ).exists()
        )


class AdvancedCommercialDocumentTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Advanced Buyer", email="advanced@example.com"
        )
        self.user = User.objects.create_user(
            "advanced-staff", password="pw", is_staff=True
        )
        self.client.force_login(self.user)

    def make_document(self, **overrides):
        values = {
            "doc_type": CommercialDocument.TYPE_INVOICE,
            "number": allocate_document_number("INV"),
            "customer": self.customer,
            "customer_name": self.customer.name,
            "status": CommercialDocument.STATUS_DRAFT,
            "tax_rate": Decimal("18"),
            "created_by": self.user,
        }
        values.update(overrides)
        return CommercialDocument.objects.create(**values)

    def test_advanced_pricing_calculation(self):
        document = self.make_document(
            discount_type=CommercialDocument.DISCOUNT_PERCENT,
            discount_value=Decimal("10"),
            shipping_amount=Decimal("10"),
            other_charges=Decimal("5"),
            withholding_tax_rate=Decimal("5"),
        )
        CommercialLine.objects.create(
            document=document,
            description="Discounted item",
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            discount_type=CommercialDocument.DISCOUNT_PERCENT,
            discount_value=Decimal("10"),
        )
        document.recalculate_from_lines()
        self.assertEqual(document.subtotal, Decimal("180.00"))
        self.assertEqual(document.discount_amount, Decimal("18.00"))
        self.assertEqual(document.tax_amount, Decimal("31.86"))
        self.assertEqual(document.withholding_tax_amount, Decimal("10.44"))
        self.assertEqual(document.total, Decimal("198.42"))

    def test_tax_inclusive_pricing_extracts_tax(self):
        document = self.make_document(
            pricing_mode=CommercialDocument.PRICING_INCLUSIVE
        )
        CommercialLine.objects.create(
            document=document,
            description="Tax inclusive item",
            quantity=Decimal("1"),
            unit_price=Decimal("118"),
        )
        document.recalculate_from_lines()
        self.assertEqual(document.subtotal, Decimal("100.00"))
        self.assertEqual(document.tax_amount, Decimal("18.00"))
        self.assertEqual(document.total, Decimal("118.00"))

    def test_credit_note_totals_are_negative(self):
        document = self.make_document(
            doc_type=CommercialDocument.TYPE_CREDIT_NOTE,
            number=allocate_document_number("CRN"),
        )
        CommercialLine.objects.create(
            document=document,
            description="Returned item",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
        )
        document.recalculate_from_lines()
        self.assertEqual(document.subtotal, Decimal("-100.00"))
        self.assertEqual(document.tax_amount, Decimal("-18.00"))
        self.assertEqual(document.total, Decimal("-118.00"))

    def test_issue_locks_document_snapshots_revision_and_posts_only_own_stock(self):
        category = Category.objects.create(name="Issue", slug="issue-stock")
        product = Product.objects.create(
            category=category,
            name="Tracked",
            slug="tracked-issue",
            price=Decimal("50"),
            stock_quantity=10,
            kind=Product.KIND_PHYSICAL,
        )
        document = self.make_document()
        CommercialLine.objects.create(
            document=document,
            product=product,
            source_type=CommercialLine.SOURCE_STOCK,
            description="Own stock",
            quantity=Decimal("2"),
            unit_price=Decimal("50"),
        )
        CommercialLine.objects.create(
            document=document,
            product=product,
            source_type=CommercialLine.SOURCE_EXTERNAL,
            supplier_name="Neighbour",
            description="External item",
            quantity=Decimal("3"),
            unit_price=Decimal("60"),
        )
        document.recalculate_from_lines()
        document.save()
        response = self.client.post(reverse("staff_document_issue", args=[document.pk]))
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        product.refresh_from_db()
        self.assertTrue(document.is_locked)
        self.assertEqual(document.status, CommercialDocument.STATUS_ISSUED)
        self.assertEqual(product.stock_quantity, 8)
        self.assertEqual(DocumentRevision.objects.filter(document=document).count(), 1)

    def test_duplicate_creates_editable_draft_with_lines(self):
        document = self.make_document(status=CommercialDocument.STATUS_ISSUED)
        CommercialLine.objects.create(
            document=document,
            description="Copy me",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
        )
        response = self.client.post(
            reverse("staff_document_duplicate", args=[document.pk])
        )
        self.assertEqual(response.status_code, 302)
        duplicate = CommercialDocument.objects.exclude(pk=document.pk).get()
        self.assertEqual(duplicate.status, CommercialDocument.STATUS_DRAFT)
        self.assertEqual(duplicate.lines.get().description, "Copy me")

    def test_overpayment_creates_customer_credit(self):
        document = self.make_document(
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("100"),
        )
        response = self.client.post(
            reverse("staff_document_payment", args=[document.pk]),
            {
                "amount": "125",
                "method": DocumentPayment.METHOD_CASH,
                "reference": "OVERPAY",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        credit = CustomerCredit.objects.get()
        self.assertEqual(document.amount_paid, Decimal("100"))
        self.assertEqual(credit.remaining_amount, Decimal("25"))

    def test_account_payment_allocates_multiple_invoices_and_saves_remainder(self):
        first = self.make_document(
            number=allocate_document_number("INV"),
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("60"),
        )
        second = self.make_document(
            number=allocate_document_number("INV"),
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("50"),
        )
        response = self.client.post(
            reverse("staff_account_payment_create"),
            {
                "customer": str(self.customer.pk),
                "customer_name": self.customer.name,
                "amount": "125",
                "method": DocumentPayment.METHOD_TRANSFER,
                "reference": "BULK",
                "note": "",
                f"allocation_{first.pk}": "60",
                f"allocation_{second.pk}": "50",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AccountPayment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 2)
        self.assertEqual(CustomerCredit.objects.get().remaining_amount, Decimal("15"))

    def test_authorised_revision_preserves_snapshot_and_unlocks(self):
        permission = Permission.objects.get(codename="revise_issued_document")
        self.user.user_permissions.add(permission)
        document = self.make_document(
            status=CommercialDocument.STATUS_ISSUED,
            locked_at=timezone.now(),
            locked_by=self.user,
        )
        CommercialLine.objects.create(
            document=document,
            description="Original",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
        )
        response = self.client.post(
            reverse("staff_document_revise", args=[document.pk]),
            {"reason": "Customer requested a change"},
        )
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertFalse(document.is_locked)
        self.assertEqual(document.status, CommercialDocument.STATUS_DRAFT)
        self.assertEqual(document.revisions.get().snapshot["lines"][0]["description"], "Original")

    def test_document_template_can_store_repeat_lines(self):
        template = DocumentTemplate.objects.create(
            name="Repeat service",
            doc_type=CommercialDocument.TYPE_QUOTE,
            tax_rate=Decimal("18"),
            lines=[{"description": "Site visit", "quantity": "1", "unit_price": "50"}],
            created_by=self.user,
        )
        self.assertEqual(template.lines[0]["description"], "Site visit")

    def test_receipt_creation_records_tendered_payment_and_change(self):
        document = self.make_document(
            doc_type=CommercialDocument.TYPE_RECEIPT,
            number=allocate_document_number("REC"),
            amount_tendered=Decimal("120"),
            receipt_payment_method=DocumentPayment.METHOD_CASH,
            receipt_payment_reference="COUNTER",
        )
        CommercialLine.objects.create(
            document=document,
            description="Counter item",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            tax_exempt=True,
        )
        document.recalculate_from_lines()
        document.save()
        from billing.views import _record_receipt_payment

        _record_receipt_payment(document, self.user)
        document.refresh_from_db()
        self.assertEqual(document.amount_paid, Decimal("100"))
        self.assertEqual(document.change_due, Decimal("20"))
        self.assertEqual(document.payments.get().reference, "COUNTER")
