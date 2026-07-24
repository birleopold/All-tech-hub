from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from core.forms import ContactForm
from core.models import ContactMessage


class ProductContactExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Business laptops",
            slug="business-laptops",
            description="Professional computers for work.",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="HP ProBook 440 G2",
            slug="hp-probook-440-g2",
            sku="HP-440-G2",
            short_description="A practical business laptop for everyday office work.",
            description="Dependable performance, useful connectivity and professional support.",
            price=Decimal("850000.00"),
            stock_quantity=2,
            reorder_level=1,
            is_published=True,
        )

    def test_product_detail_renders_mature_buying_experience(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "public-product-page")
        self.assertContains(response, "Purchase options")
        self.assertContains(response, "Buy with confidence")
        self.assertContains(response, "Request formal quote")
        self.assertContains(response, "public_detail_contact.css")
        self.assertContains(response, "public_detail_contact.js")
        self.assertContains(response, "type=quote&amp;product=hp-probook-440-g2")
        self.assertTrue(response.context["product"].public_available)

    def test_contact_prefills_product_and_quote_context(self):
        response = self.client.get(
            reverse("contact"),
            {"type": ContactForm.REQUEST_QUOTE, "product": self.product.slug},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "public-contact-page")
        self.assertContains(response, "Start with the right request")
        self.assertContains(response, self.product.name)
        self.assertEqual(response.context["contact_product"], self.product)
        self.assertEqual(
            response.context["form"].initial["request_type"],
            ContactForm.REQUEST_QUOTE,
        )
        self.assertIn(self.product.name, response.context["form"].initial["subject"])

    @patch("marketing.services.create_lead_from_contact")
    def test_contact_post_categorises_saved_subject(self, create_lead):
        response = self.client.post(
            reverse("contact"),
            {
                "request_type": ContactForm.REQUEST_REPAIR,
                "name": "Amina",
                "email": "amina@example.com",
                "phone": "0700000000",
                "subject": "Laptop does not power on",
                "message": "The charging light comes on but the laptop will not start.",
            },
        )

        self.assertRedirects(response, reverse("contact"))
        message = ContactMessage.objects.get()
        self.assertEqual(message.subject, "Repair or diagnostics: Laptop does not power on")
        create_lead.assert_called_once()

    @patch("marketing.services.create_lead_from_contact")
    def test_contact_post_remains_compatible_without_request_type(self, create_lead):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Daniel",
                "email": "daniel@example.com",
                "phone": "",
                "subject": "General question",
                "message": "Please advise on your available support services.",
            },
        )

        self.assertRedirects(response, reverse("contact"))
        self.assertTrue(
            ContactMessage.objects.filter(subject="Other request: General question").exists()
        )
        create_lead.assert_called_once()
