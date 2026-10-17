"""Phase 5 regression checks: permission-aware search and reusable CRM workflows."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument
from commerce.models import Order
from core.models import ContactMessage, SupportTicket
from crm.models import Customer
from marketing.models import MarketingLead
from operations.models import JobCard


@override_settings(SECURE_SSL_REDIRECT=False)
class StaffCommandCentreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_user(
            username="phase5-admin", password="pw", is_staff=True, is_superuser=True
        )
        cls.limited = users.objects.create_user(
            username="phase5-limited", password="pw", is_staff=True
        )
        cls.customer = Customer.objects.create(
            name="Priority Client", email="priority@company.example"
        )
        cls.lead = MarketingLead.objects.create(
            name="Priority Client", email=cls.customer.email,
            response_due_at=timezone.now() - timedelta(hours=2),
        )
        cls.enquiry = ContactMessage.objects.create(
            name="Priority Client", email=cls.customer.email,
            subject="Workstation request", message="Please quote a workstation",
        )
        cls.order = Order.objects.create(
            customer=cls.customer, reference="ORD-PHASE5-ONE",
            contact_name=cls.customer.name, contact_email=cls.customer.email,
        )
        cls.document = CommercialDocument.objects.create(
            customer=cls.customer, customer_name=cls.customer.name,
            doc_type=CommercialDocument.TYPE_QUOTE,
            number="QUO-PHASE5-ONE",
        )
        cls.job = JobCard.objects.create(customer=cls.customer, title="Laptop repair")
        cls.ticket = SupportTicket.objects.create(
            customer=cls.customer, subject="Laptop question",
            description="Check this device",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_staff_search_finds_leads_and_enquiries(self):
        r = self.client.get(reverse("staff_search"), {"q": "Priority Client"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.lead, r.context["results"]["leads"])
        self.assertIn(self.enquiry, r.context["results"]["enquiries"])
        self.assertContains(r, reverse("staff_marketing_lead_edit", args=[self.lead.pk]))
        self.assertContains(r, "Workstation request")

    def test_search_permissions_hide_sensitive_sales_records(self):
        self.client.force_login(self.limited)
        r = self.client.get(reverse("staff_search"), {"q": "Priority Client"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("leads", r.context["results"])
        self.assertNotIn("enquiries", r.context["results"])
        self.assertNotContains(r, self.customer.email)
        self.assertNotContains(r, "Create a new permitted record")
        self.limited.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="crm", codename="view_customer"
            )
        )
        self.client.force_login(get_user_model().objects.get(pk=self.limited.pk))
        r = self.client.get(reverse("staff_search"), {"q": "Priority Client"})
        self.assertIn(self.customer, r.context["results"]["customers"])
        self.assertNotIn("leads", r.context["results"])

    def test_customer_shortcuts_prefill_existing_record_forms(self):
        r = self.client.get(
            reverse("staff_customer_detail", args=[self.customer.pk])
        )
        self.assertEqual(r.status_code, 200)
        for name in (
            "staff_document_create", "staff_job_create", "staff_ticket_create"
        ):
            url = reverse(name)
            self.assertContains(r, f"{url}?customer={self.customer.pk}")
            opened = self.client.get(url, {"customer": self.customer.pk})
            self.assertEqual(opened.status_code, 200)
            self.assertEqual(
                opened.context["form"].initial["customer"], self.customer.pk
            )
            unknown = self.client.get(url, {"customer": "99999999"})
            self.assertEqual(unknown.status_code, 200)
            self.assertNotEqual(
                unknown.context["form"].initial.get("customer"), 99999999
            )

    def test_customer_timeline_contains_order_repair_ticket_and_quote(self):
        r = self.client.get(
            reverse("staff_customer_detail", args=[self.customer.pk])
        )
        kinds = {e["kind"] for e in r.context["customer_timeline"]}
        self.assertIn("Repair", kinds)
        self.assertIn("Support", kinds)
        self.assertIn("Order", kinds)
        urls = {e["url"] for e in r.context["customer_timeline"]}
        self.assertIn(reverse("staff_job_detail", args=[self.job.pk]), urls)
        self.assertIn(reverse("staff_ticket_detail", args=[self.ticket.pk]), urls)

    def test_lead_attention_includes_first_response_and_due_follow_up(self):
        other = MarketingLead.objects.create(
            name="Followup example",
            status=MarketingLead.STATUS_CONTACTED,
            next_follow_up_at=timezone.now() - timedelta(minutes=5),
        )
        r = self.client.get(
            reverse("staff_marketing_leads"), {"follow_up": "needs_attention"}
        )
        self.assertEqual(r.status_code, 200)
        ids = {x.pk for x in r.context["object_list"]}
        self.assertEqual(ids, {self.lead.pk, other.pk})

    def test_filtered_leads_keep_filters_on_second_page(self):
        for i in range(32):
            MarketingLead.objects.create(
                name=f"Paging client {i:02d}",
                assigned_to=self.admin,
            )
        params = {"q": "Paging client", "status": "new", "owner": "mine"}
        first = self.client.get(reverse("staff_marketing_leads"), params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.context["paginator"].count, 32)
        self.assertContains(first, "owner=mine")
        second = self.client.get(
            reverse("staff_marketing_leads"), {**params, "page": 2}
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.context["object_list"]), 2)
        self.assertContains(second, "page=1")

    def test_dashboard_shows_role_relevant_actions(self):
        r = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "My work areas")
        self.assertContains(r, "?owner=mine")
        self.assertContains(r, "?follow_up=needs_attention")
