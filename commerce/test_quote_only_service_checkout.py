"""Customer-to-staff quote-only service checkout protections."""
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from commerce import cart as cart_mod


@override_settings(SECURE_SSL_REDIRECT=False)
class QuoteOnlyServiceCheckoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="IT Services", slug="quote-only-services")
        cls.unpriced = Product.objects.create(
            category=category, kind=Product.KIND_SERVICE,
            name="Unquoted network installation", slug="unquoted-installation",
            price=Decimal("0.00"), track_inventory=False,
            is_published=True,
        )
        cls.paid = Product.objects.create(
            category=category, kind=Product.KIND_SERVICE,
            name="Fixed-price inspection", slug="fixed-price-inspection",
            price=Decimal("50000.00"), track_inventory=False,
            is_published=True,
        )
        cls.variant_service = Product.objects.create(
            category=category, kind=Product.KIND_SERVICE,
            name="Installation variants", slug="installation-variants",
            price=Decimal("0.00"), track_inventory=False, is_published=True,
        )
        cls.zero_variant = ProductVariant.objects.create(
            product=cls.variant_service, name="Site assessment",
            sku="SITE-ASSESSMENT", price=Decimal("0.00"),
            is_active=True, track_inventory=False
        )

    def test_unquoted_service_page_links_to_product_specific_quote(self):
        response = self.client.get(self.unpriced.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request service quotation")
        self.assertContains(response, "Quotation required before booking")
        self.assertContains(response, "Request quote")
        self.assertContains(response, "type=quote&amp;product=unquoted-installation")
        enquiry = self.client.get(
            reverse("contact"),
            {"type": "quote", "product": self.unpriced.slug},
        )
        self.assertEqual(enquiry.status_code, 200)
        self.assertEqual(
            enquiry.context["form"].initial["request_type"], "quote"
        )
        self.assertIn(
            "Location or site:", enquiry.context["form"].initial["message"]
        )
        self.assertEqual(
            enquiry.context["contact_product"].pk, self.unpriced.pk
        )
        self.assertNotContains(
            response,
            f'action="{reverse("cart_add", args=[self.unpriced.pk])}"',
        )

    def test_direct_zero_service_cart_posts_are_redirected_to_quote(self):
        response = self.client.post(
            reverse("cart_add", args=[self.unpriced.pk]), {"quantity": 1}
        )
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response.url)
        self.assertEqual(url.path, reverse("contact"))
        self.assertEqual(parse_qs(url.query)["product"], ["unquoted-installation"])
        self.assertEqual(parse_qs(url.query)["type"], ["quote"])
        self.assertEqual(cart_mod.get_cart(self.client.session), {})

    def test_unquoted_variant_cannot_be_added_at_zero_price(self):
        response = self.client.post(
            reverse("cart_add", args=[self.variant_service.pk]),
            {"variant_id": self.zero_variant.pk, "quantity": 1},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.url).path, reverse("contact"))
        self.assertEqual(cart_mod.get_cart(self.client.session), {})

    def test_old_unquoted_services_are_pruned_but_priced_items_survive(self):
        session = self.client.session
        cart_mod.add_product(session, self.unpriced.pk)
        cart_mod.add_product(session, self.paid.pk)
        cart_mod.add_variant(session, self.zero_variant.pk)
        session.save()
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            cart_mod.get_cart(self.client.session),
            {f"p:{self.paid.pk}": 1},
        )
        self.assertContains(response, self.paid.name)
        self.assertNotContains(response, self.unpriced.name)

    def test_checkout_refuses_old_unquoted_cart_before_creating_order(self):
        session = self.client.session
        cart_mod.add_product(session, self.unpriced.pk)
        cart_mod.add_product(session, self.paid.pk)
        session.save()
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(
            cart_mod.get_cart(self.client.session),
            {f"p:{self.paid.pk}": 1},
        )

    def test_fixed_price_service_remains_orderable(self):
        response = self.client.post(
            reverse("cart_add", args=[self.paid.pk]), {"quantity": 1}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(cart_mod.get_cart(self.client.session), {
            f"p:{self.paid.pk}": 1
        })
