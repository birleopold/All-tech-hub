from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductImage
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
        ProductImage.objects.create(
            product=cls.product,
            image="products/gallery/hp-probook-front.jpg",
            sort_order=0,
            alt_text="HP ProBook front view",
        )
        ProductImage.objects.create(
            product=cls.product,
            image="products/gallery/hp-probook-side.jpg",
            sort_order=1,
            alt_text="HP ProBook side view",
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

    def test_gallery_uses_first_available_image_as_main_image(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Image coming soon")
        self.assertContains(response, "hp-probook-front.jpg")
        self.assertContains(response, "hp-probook-side.jpg")
        self.assertEqual(response.context["gallery_count"], 2)
        self.assertEqual(
            response.context["product"].public_display_image.name,
            "products/gallery/hp-probook-front.jpg",
        )

    def test_gallery_script_prevents_thumbnail_navigation(self):
        script = (
            Path(settings.BASE_DIR) / "static" / "js" / "public_detail_contact.js"
        ).read_text(encoding="utf-8")

        self.assertIn('event.preventDefault();', script)
        self.assertIn('event.stopImmediatePropagation();', script)
        self.assertIn('replaceMainImage(button);', script)
        self.assertIn('link.classList.remove("stretched-link");', script)

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

    def test_product_enquiry_remains_linked_after_form_submission(self):
        from marketing.models import MarketingLead

        response = self.client.post(
            reverse("contact"),
            {
                "request_type": ContactForm.REQUEST_QUOTE,
                "product": self.product.slug,
                "name": "Product buyer",
                "email": "product-buyer@example.com",
                "phone": "0700000000",
                "subject": "Please quote for this laptop",
                "message": "Please confirm the current price and availability.",
            },
        )

        self.assertRedirects(response, reverse("contact"))
        message = ContactMessage.objects.get()
        lead = MarketingLead.objects.get()
        self.assertEqual(message.product, self.product)
        self.assertEqual(message.request_type, ContactForm.REQUEST_QUOTE)
        self.assertEqual(lead.product, self.product)
        self.assertEqual(lead.estimated_value, self.product.price)

    def test_unpublished_product_cannot_be_attached_to_an_enquiry(self):
        self.product.is_published = False
        self.product.save(update_fields=["is_published"])

        self.client.post(
            reverse("contact"),
            {
                "request_type": ContactForm.REQUEST_PRODUCT,
                "product": self.product.slug,
                "name": "Product buyer",
                "email": "product-buyer@example.com",
                "subject": "Is this laptop available?",
                "message": "Please let me know whether it can still be ordered.",
            },
        )

        self.assertIsNone(ContactMessage.objects.get().product)
