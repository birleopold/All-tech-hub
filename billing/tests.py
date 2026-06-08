from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from billing.models import CommercialDocument, CommercialLine, allocate_document_number
from catalog.models import Category, Product, ProductVariant
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
        response = self.client.get(url)
        self.assertRedirects(response, reverse("staff_document_edit", args=[self.doc.pk]))
        before = CommercialDocument.objects.count()
        self.doc.refresh_from_db()
        self.doc.quote_internally_approved = True
        self.doc.save()
        response = self.client.get(url)
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
        r = self.client.get(url)
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
