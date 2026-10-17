from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument
from catalog.models import Category, Product
from commerce.models import Order
from core.models import ContactMessage, StaffNotification, SupportTicket
from crm.models import Customer
from marketing.models import CampaignLink, MarketingCampaign, MarketingLead
from marketing.services import close_lead_from_order, create_quote_from_lead, process_due_lead_followups


@override_settings(MARKETING_LEAD_RESPONSE_TARGET_MINUTES=30)
class SalesLeadPipelineTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.salesperson = user_model.objects.create_user(
            username="lead-salesperson",
            email="sales@example.com",
            password="strong-test-password",
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name="Sales")
        self.salesperson.groups.add(group)

    def _send_enquiry(self, *, request_type="product", email="buyer@example.com"):
        return self.client.post(
            reverse("contact"),
            {
                "request_type": request_type,
                "name": "Interested buyer",
                "email": email,
                "phone": "0700123456",
                "subject": "Laptop enquiry",
                "message": "Please share the laptop price and available specifications.",
            },
        )

    def test_contact_is_assigned_timed_and_notifies_sales_owner(self):
        response = self._send_enquiry(request_type="quote")

        self.assertRedirects(response, reverse("contact"))
        lead = MarketingLead.objects.get()
        self.assertEqual(lead.assigned_to, self.salesperson)
        self.assertEqual(lead.request_type, "quote")
        self.assertEqual(lead.priority, MarketingLead.PRIORITY_HIGH)
        self.assertEqual(lead.next_follow_up_at, lead.response_due_at)
        self.assertLessEqual(lead.response_due_at - timezone.now(), timedelta(minutes=15))
        self.assertTrue(
            StaffNotification.objects.filter(
                recipient=self.salesperson,
                message__icontains="enquiry",
            ).exists()
        )

    def test_tracked_enquiry_uses_verified_channel(self):
        campaign = MarketingCampaign.objects.create(name="Social campaign")
        link = CampaignLink.objects.create(
            campaign=campaign,
            name="TikTok quote",
            destination_url="https://testserver/contact/",
            source="tiktok",
            medium="social",
        )
        self.client.get(reverse("marketing_track", args=[link.code]))

        self._send_enquiry(request_type="quote")

        lead = MarketingLead.objects.get()
        link.refresh_from_db()
        self.assertEqual(lead.link, link)
        self.assertEqual(lead.source, "tiktok")
        self.assertEqual(link.lead_count, 1)

    def test_quick_contact_records_response_and_closes_inbox_message(self):
        self._send_enquiry()
        lead = MarketingLead.objects.get()
        self.client.force_login(self.salesperson)

        response = self.client.post(
            reverse("staff_marketing_lead_contacted", args=[lead.pk])
        )

        self.assertRedirects(response, reverse("staff_marketing_leads"))
        lead.refresh_from_db()
        self.assertEqual(lead.status, MarketingLead.STATUS_CONTACTED)
        self.assertIsNotNone(lead.first_contacted_at)
        self.assertIsNone(lead.next_follow_up_at)
        self.assertTrue(ContactMessage.objects.get().handled)

    def test_tracked_order_does_not_close_other_campaign_lead(self):
        customer = Customer.objects.create(
            name="Shared contact", email="link-mismatch@example.com"
        )
        other_link = CampaignLink.objects.create(
            name="Unrelated referral", source="facebook", medium="social",
            destination_url="https://example.com/",
        )
        incoming = CampaignLink.objects.create(
            name="Actual referral", source="telegram", medium="social",
            destination_url="https://example.com/",
        )
        lead = MarketingLead.objects.create(
            name="Shared contact", email=customer.email,
            source="facebook", medium="social", link=other_link,
        )
        order = Order.objects.create(
            customer=customer, reference="ORD-LEAD-LINK-MISMATCH",
            contact_name=customer.name, contact_email=customer.email,
            marketing_link=incoming,
        )
        self.assertIsNone(close_lead_from_order(order))
        lead.refresh_from_db()
        self.assertEqual(lead.status, MarketingLead.STATUS_NEW)
        self.assertIsNone(lead.won_order_id)

    def test_multiple_same_email_leads_are_not_automatically_linked_to_order(self):
        customer = Customer.objects.create(
            name="Ambiguous contact", email="ambiguous-leads@example.com"
        )
        first = MarketingLead.objects.create(
            name="First request", email=customer.email
        )
        second = MarketingLead.objects.create(
            name="Second request", email=customer.email
        )
        order = Order.objects.create(
            customer=customer, reference="ORD-LEAD-AMBIGUOUS",
            contact_name=customer.name, contact_email=customer.email,
        )
        self.assertIsNone(close_lead_from_order(order))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.won_order_id)
        self.assertIsNone(second.won_order_id)

    def test_matching_order_marks_lead_won_and_links_order(self):
        self._send_enquiry()
        customer = Customer.objects.create(name="Interested buyer", email="buyer@example.com")
        order = Order.objects.create(
            reference="ORD-LEAD-001",
            customer=customer,
            contact_name=customer.name,
            contact_email=customer.email,
            total=Decimal("1250000.00"),
        )

        lead = close_lead_from_order(order)

        self.assertEqual(lead.status, MarketingLead.STATUS_WON)
        self.assertEqual(lead.won_order, order)
        self.assertEqual(lead.estimated_value, Decimal("1250000.00"))
        self.assertTrue(ContactMessage.objects.get().handled)

    def test_staff_cannot_assign_lead_to_non_staff_account(self):
        from marketing.forms import MarketingLeadForm

        ordinary = get_user_model().objects.create_user(
            username="ordinary-customer", password="strong-test-password"
        )
        form = MarketingLeadForm()

        self.assertNotIn(ordinary, form.fields["assigned_to"].queryset)

    def test_product_enquiry_stays_visible_in_inbox_and_support_ticket(self):
        category = Category.objects.create(name="Computers", slug="computers")
        product = Product.objects.create(
            category=category,
            name="Dell Latitude 5420",
            slug="dell-latitude-5420",
            sku="DELL-5420",
            price=Decimal("1850000.00"),
            stock_quantity=4,
            is_published=True,
        )
        self.client.post(
            reverse("contact"),
            {
                "request_type": "quote",
                "product": product.slug,
                "name": "Interested buyer",
                "email": "buyer@example.com",
                "phone": "0700123456",
                "subject": "Please quote for this laptop",
                "message": "Please share the laptop price and available specifications.",
            },
        )
        message = ContactMessage.objects.get()
        self.client.force_login(self.salesperson)

        inbox = self.client.get(reverse("staff_contact_messages"))

        self.assertContains(inbox, product.name)
        self.assertContains(inbox, product.sku)
        self.assertContains(inbox, "4 in stock")

        response = self.client.post(
            reverse("staff_contact_to_ticket", args=[message.pk])
        )

        ticket = SupportTicket.objects.get()
        self.assertRedirects(response, reverse("staff_ticket_detail", args=[ticket.pk]))
        self.assertEqual(ticket.related_product, product)
        self.assertEqual(ticket.priority, SupportTicket.PRIORITY_HIGH)
        self.assertContains(self.client.get(response.url), product.name)

    def test_enquiry_becomes_one_customer_linked_quotation(self):
        category = Category.objects.create(name="Quote computers", slug="quote-computers")
        product = Product.objects.create(category=category, name="Business laptop", slug="business-laptop", price=Decimal("1850000.00"), stock_quantity=3)
        lead = MarketingLead.objects.create(name="Interested buyer", email="buyer@example.com", product=product, assigned_to=self.salesperson)

        first = create_quote_from_lead(lead, actor=self.salesperson)
        second = create_quote_from_lead(lead, actor=self.salesperson)

        lead.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(lead.quoted_document, first)
        self.assertEqual(first.customer.email, "buyer@example.com")
        self.assertEqual(first.lines.get().product, product)
        self.assertEqual(lead.status, MarketingLead.STATUS_QUALIFIED)

    def test_quote_conversion_does_not_choose_first_duplicate_customer(self):
        user_model = get_user_model()
        actor = self.salesperson
        Customer.objects.create(name="A", email="duplicate@example.com")
        Customer.objects.create(name="B", email="DUPLICATE@example.com")
        lead = MarketingLead.objects.create(
            name="Ambiguous customer", email="duplicate@example.com",
        )
        with self.assertRaisesMessage(ValueError, "More than one customer"):
            create_quote_from_lead(lead, actor=actor)
        lead.refresh_from_db()
        self.assertIsNone(lead.quoted_document)
        self.assertEqual(
            CommercialDocument.objects.filter(
                customer__email__iexact="duplicate@example.com"
            ).count(), 0,
        )

    def test_overdue_enquiry_is_reminded_and_escalated_once(self):
        manager = get_user_model().objects.create_user(username="lead-manager", password="strong-test-password", is_staff=True, is_superuser=True)
        lead = MarketingLead.objects.create(name="Overdue buyer", email="late@example.com", assigned_to=self.salesperson,
            response_due_at=timezone.now() - timedelta(hours=2), next_follow_up_at=timezone.now() - timedelta(hours=2))

        first = process_due_lead_followups()
        second = process_due_lead_followups()

        lead.refresh_from_db()
        self.assertEqual(first, {"reminded": 1, "escalated": 1})
        self.assertEqual(second, {"reminded": 0, "escalated": 0})
        self.assertIsNotNone(lead.escalated_at)
        self.assertTrue(StaffNotification.objects.filter(recipient=manager, message__icontains="Escalated").exists())
