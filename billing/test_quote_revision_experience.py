"""Quotation version comparison, customer ownership and safe acceptance."""
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument, CommercialLine, DocumentRevision
from crm.models import Customer


@override_settings(SECURE_SSL_REDIRECT=False)
class QuoteRevisionExperienceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_superuser(
            username="revision-staff", email="revision-staff@example.com", password="pw"
        )
        self.helper = User.objects.create_user(
            username="revision-helper", is_staff=True, password="pw"
        )
        self.owner = User.objects.create_user(username="revision-owner", password="pw")
        self.outsider = User.objects.create_user(username="revision-outsider", password="pw")
        self.customer = Customer.objects.create(
            name="Quotation owner", email="q-owner@example.com", user=self.owner
        )
        Customer.objects.create(
            name="Other customer", email="q-other@example.com", user=self.outsider
        )
        self.quote = CommercialDocument.objects.create(
            number="QUO-VERSION-COMPARE", customer=self.customer,
            doc_type=CommercialDocument.TYPE_QUOTE,
            status=CommercialDocument.STATUS_ISSUED,
            locked_at=timezone.now(), locked_by=self.staff,
            total="250000.00", subtotal="250000.00",
            quote_requires_internal_approval=True,
            quote_internally_approved=True,
            quote_approved_by=self.staff,
            quote_approved_at=timezone.now(),
            quote_requires_customer_acceptance=True,
            quote_customer_token=uuid4(),
        )
        self.line = CommercialLine.objects.create(
            document=self.quote, description="Original laptop SSD",
            quantity=1, unit_price="250000.00",
        )
        snapshot = self.quote.snapshot_data()
        snapshot["lines"][0]["supplier_name"] = "PRIVATE-SUPPLIER-RED"
        snapshot["lines"][0]["unit_cost"] = "999991"
        self.revision = DocumentRevision.objects.create(
            document=self.quote,
            revision_number=1,
            reason="Client requested larger SSD",
            snapshot=snapshot,
            created_by=self.staff,
        )
        self.line.description = "Larger laptop SSD"
        self.line.unit_price = "320000.00"
        self.line.save()
        self.quote.total = "320000.00"
        self.quote.subtotal = "320000.00"
        self.quote.revision_number = 1
        self.quote.save(update_fields=["total", "subtotal", "revision_number", "updated_at"])

    def staff_url(self):
        return reverse("staff_document_revision_compare", args=[
            self.quote.pk, self.revision.revision_number
        ])

    def owner_url(self):
        return reverse("portal_quote_revision_compare", args=[
            self.quote.pk, self.revision.revision_number
        ])

    def acceptance_url(self):
        return reverse("quote_customer_portal", args=[self.quote.quote_customer_token])

    def test_staff_can_compare_immutable_version_and_current_terms(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.staff_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original laptop SSD")
        self.assertContains(response, "Larger laptop SSD")
        self.assertContains(response, "250000.00")
        self.assertContains(response, "320000.00")
        self.assertContains(response, "Client requested larger SSD")
        self.assertContains(response, "document has changed")
        self.assertNotContains(response, "PRIVATE-SUPPLIER-RED")
        self.assertNotContains(response, "999991")
        self.assertIn("no-store", response["Cache-Control"])

    def test_customer_can_see_only_own_issued_quote_history(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.owner_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original laptop SSD")
        self.assertContains(response, "Larger laptop SSD")
        self.assertNotContains(response, "Client requested larger SSD")
        self.assertNotContains(response, "PRIVATE-SUPPLIER-RED")
        self.assertNotContains(response, "999991")
        listing = self.client.get(reverse("portal_documents"))
        self.assertContains(listing, "Version history")
        self.assertContains(listing, self.owner_url())
        self.assertContains(listing, "Review / accept")
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.owner_url()).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.owner_url()).status_code, 302)

    def test_staff_without_view_permission_cannot_open_snapshot(self):
        self.client.force_login(self.helper)
        self.assertEqual(self.client.get(self.staff_url()).status_code, 404)
        self.assertEqual(self.client.get(self.owner_url()).status_code, 302)

    def test_draft_unapproved_or_wrong_revision_is_inaccessible(self):
        self.client.force_login(self.owner)
        self.quote.status = CommercialDocument.STATUS_DRAFT
        self.quote.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.owner_url()).status_code, 404)
        self.quote.status = CommercialDocument.STATUS_ISSUED
        self.quote.quote_internally_approved = False
        self.quote.save(update_fields=["status", "quote_internally_approved"])
        self.assertEqual(self.client.get(self.owner_url()).status_code, 404)
        self.quote.quote_internally_approved = True
        self.quote.save(update_fields=["quote_internally_approved"])
        invalid = reverse("portal_quote_revision_compare", args=[self.quote.pk, 999])
        self.assertEqual(self.client.get(invalid).status_code, 404)
        self.revision.snapshot["status"] = CommercialDocument.STATUS_DRAFT
        self.revision.save(update_fields=["snapshot"])
        self.assertEqual(self.client.get(self.owner_url()).status_code, 404)

    def test_pending_draft_unapproved_and_expired_quotes_reject_acceptance(self):
        for state, approved, expired in (
            (CommercialDocument.STATUS_DRAFT, True, False),
            (CommercialDocument.STATUS_ISSUED, False, False),
            (CommercialDocument.STATUS_ISSUED, True, True),
        ):
            with self.subTest(state=state, approved=approved, expired=expired):
                self.quote.status = state
                self.quote.quote_internally_approved = approved
                self.quote.due_date = (
                    timezone.localdate() - timedelta(days=1) if expired else None
                )
                self.quote.quote_customer_accepted = None
                self.quote.save(update_fields=[
                    "status", "quote_internally_approved", "due_date",
                    "quote_customer_accepted",
                ])
                self.assertEqual(self.client.get(self.acceptance_url()).status_code, 404)
                self.assertEqual(self.client.post(self.acceptance_url(), {
                    "action": "accept", "signature_name": "Quotation owner"
                }).status_code, 404)
                self.quote.refresh_from_db()
                self.assertIsNone(self.quote.quote_customer_accepted)

    def test_customer_can_accept_valid_current_quote_only_once(self):
        response = self.client.post(self.acceptance_url(), {
            "action": "accept", "signature_name": "Quotation owner"
        })
        self.assertEqual(response.status_code, 302)
        self.quote.refresh_from_db()
        self.assertIs(self.quote.quote_customer_accepted, True)
        result = self.client.post(self.acceptance_url(), {
            "action": "decline", "decline_reason": "Change my mind"
        })
        self.assertEqual(result.status_code, 200)
        self.quote.refresh_from_db()
        self.assertIs(self.quote.quote_customer_accepted, True)

    def test_staff_can_enable_link_only_after_valid_issue_and_approval(self):
        self.client.force_login(self.staff)
        url = reverse("staff_document_quote_customer_link", args=[self.quote.pk])
        self.quote.status = CommercialDocument.STATUS_DRAFT
        self.quote.save(update_fields=["status"])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, CommercialDocument.STATUS_DRAFT)
        self.quote.status = CommercialDocument.STATUS_ISSUED
        self.quote.quote_internally_approved = False
        self.quote.save(update_fields=["status", "quote_internally_approved"])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.quote.refresh_from_db()
        self.assertFalse(self.quote.quote_internally_approved)
        self.quote.quote_internally_approved = True
        self.quote.save(update_fields=["quote_internally_approved"])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.quote_requires_customer_acceptance)
        self.assertEqual(self.client.get(self.acceptance_url()).status_code, 200)
