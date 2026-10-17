"""Cross-customer isolation and linked helpdesk customer journeys."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from billing.models import CommercialDocument
from commerce.models import Order, OrderStatusEvent
from core.forms import PortalSupportTicketForm, StaffSupportTicketForm
from core.models import SupportTicket, TicketComment
from crm.models import Customer
from operations.models import JobCard, JobStatusEvent
from portal.activity import customer_service_activity


@override_settings(SECURE_SSL_REDIRECT=False)
class CustomerServiceHubTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="service-portal-owner", password="pw",
            email="service-owner@example.com",
        )
        cls.other_user = User.objects.create_user(
            username="service-portal-other", password="pw",
            email="service-other@example.com",
        )
        cls.customer = Customer.objects.create(
            name="Customer A", email=cls.user.email, user=cls.user
        )
        cls.other_customer = Customer.objects.create(
            name="Customer B", email=cls.other_user.email, user=cls.other_user
        )
        cls.job = JobCard.objects.create(
            customer=cls.customer, title="Repair A"
        )
        cls.other_job = JobCard.objects.create(
            customer=cls.other_customer, title="Private Repair B"
        )
        cls.order = Order.objects.create(
            reference="ORD-SERVICE-A", customer=cls.customer,
            contact_name=cls.customer.name, contact_email=cls.customer.email,
        )
        cls.other_order = Order.objects.create(
            reference="ORD-SERVICE-B", customer=cls.other_customer,
            contact_name=cls.other_customer.name, contact_email=cls.other_customer.email,
        )
        cls.invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-SERVICE-A", customer=cls.customer,
            order=cls.order, status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("25000.00"),
        )
        cls.other_invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-SERVICE-B", customer=cls.other_customer,
            order=cls.other_order, status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("85000.00"),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _data(self, **updates):
        data = {
            "category": SupportTicket.CATEGORY_BILLING,
            "subject": "I need help with this document",
            "description": "Please clarify the labour charge.",
            "priority": SupportTicket.PRIORITY_NORMAL,
            "related_order": str(self.order.pk),
            "related_job": str(self.job.pk),
            "related_document": str(self.invoice.pk),
        }
        data.update(updates)
        return data

    def test_owned_job_and_invoice_prefill_and_help_links(self):
        response = self.client.get(
            reverse("portal_ticket_create"),
            {"job": self.job.pk, "document": self.invoice.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["related_job"], self.job.pk)
        self.assertEqual(
            response.context["form"].initial["related_document"], self.invoice.pk
        )
        self.assertEqual(
            response.context["form"].initial["related_order"], self.order.pk
        )
        self.assertContains(response, "INV-SERVICE-A")
        self.assertNotContains(response, "INV-SERVICE-B")

        job_detail = self.client.get(reverse("portal_job_detail", args=[self.job.pk]))
        self.assertContains(job_detail, "Ask about this repair")
        self.assertContains(job_detail, f"?job={self.job.pk}")
        documents = self.client.get(reverse("portal_documents"))
        self.assertContains(documents, f"?document={self.invoice.pk}")

    def test_support_request_saves_customer_owned_links(self):
        response = self.client.post(reverse("portal_ticket_create"), self._data())
        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get(customer=self.customer)
        self.assertEqual(ticket.related_job_id, self.job.pk)
        self.assertEqual(ticket.related_document_id, self.invoice.pk)
        detail = self.client.get(reverse("portal_ticket_detail", args=[ticket.pk]))
        self.assertContains(detail, reverse("portal_job_detail", args=[self.job.pk]))
        self.assertContains(detail, reverse("portal_document_pdf", args=[self.invoice.pk]))
        job_detail = self.client.get(reverse("portal_job_detail", args=[self.job.pk]))
        self.assertContains(job_detail, ticket.reference)

    def test_another_customer_records_cannot_be_prefilled_or_submitted(self):
        response = self.client.get(reverse("portal_ticket_create"), {
            "job": self.other_job.pk, "document": self.other_invoice.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("related_job", response.context["form"].initial)
        self.assertNotIn("related_document", response.context["form"].initial)
        self.assertNotContains(response, "Private Repair B")
        self.assertNotContains(response, "INV-SERVICE-B")
        rejected = self.client.post(
            reverse("portal_ticket_create"),
            self._data(related_job=str(self.other_job.pk)),
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(rejected, "Select a valid choice")
        self.assertFalse(SupportTicket.objects.filter(customer=self.customer).exists())

    def test_document_order_mismatch_is_rejected(self):
        form = PortalSupportTicketForm(
            data=self._data(related_order=str(self.other_order.pk)),
            customer=self.customer,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("related_order", form.errors)

    def test_model_and_staff_editor_reject_cross_customer_links(self):
        ticket = SupportTicket(
            customer=self.customer, subject="Mismatch",
            description="A confidential record cannot be linked.",
            related_job=self.other_job,
        )
        with self.assertRaises(ValidationError):
            ticket.full_clean()
        staff_form = StaffSupportTicketForm(
            data={
                "customer": self.customer.pk,
                "category": SupportTicket.CATEGORY_GENERAL,
                "subject": "Wrong linked record",
                "description": "Please review",
                "status": SupportTicket.STATUS_OPEN,
                "priority": SupportTicket.PRIORITY_NORMAL,
                "related_document": self.other_invoice.pk,
                "related_job": self.other_job.pk,
            }
        )
        self.assertFalse(staff_form.is_valid())
        self.assertIn("related_document", staff_form.errors)

    def test_recent_activity_excludes_private_replies_and_other_customers(self):
        OrderStatusEvent.objects.create(
            order=self.order, from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CONFIRMED, visible_to_customer=True,
        )
        OrderStatusEvent.objects.create(
            order=self.order, from_status=Order.STATUS_CONFIRMED,
            to_status=Order.STATUS_PROCESSING, visible_to_customer=False,
        )
        JobStatusEvent.objects.create(
            job=self.job, from_status=JobCard.STATUS_INTAKE,
            to_status=JobCard.STATUS_DIAGNOSING,
        )
        own_ticket = SupportTicket.objects.create(
            customer=self.customer, subject="Visible ticket", description="Need help"
        )
        TicketComment.objects.create(
            ticket=own_ticket, body="Customer visible response", is_internal=False
        )
        TicketComment.objects.create(
            ticket=own_ticket, body="Internal-only message", is_internal=True
        )
        SupportTicket.objects.create(
            customer=self.other_customer, subject="Secret other ticket",
            description="Sensitive",
        )
        activity = customer_service_activity(self.customer, limit=40)
        labels = [entry["label"] for entry in activity]
        self.assertIn(f"Repair {self.job.number} updated", labels)
        self.assertIn("Order ORD-SERVICE-A updated", labels)
        self.assertIn(f"Reply on {own_ticket.reference}", labels)
        self.assertIn("Document INV-SERVICE-A", labels)
        self.assertNotIn("Document INV-SERVICE-B", labels)
        self.assertNotIn("Order ORD-SERVICE-B", labels)
        self.assertFalse(any("other ticket" in s.lower() for s in labels))
        self.assertEqual(
            len([s for s in labels if s.startswith("Order ORD-SERVICE-A updated")]), 1
        )
        self.assertEqual(len([s for s in labels if s.startswith("Reply on")]), 1)

        page = self.client.get(reverse("portal_home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Recent updates")
        self.assertNotContains(page, "INV-SERVICE-B")

    def test_anonymous_visitors_do_not_receive_activity(self):
        self.client.logout()
        page = self.client.get(reverse("portal_home"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "INV-SERVICE-A")
        self.assertIsNone(page.context["portal_customer"])
