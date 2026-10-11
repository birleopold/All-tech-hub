from decimal import Decimal
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from catalog.templatetags.product_ordering import product_order_links
from core.models import CompanySettings
from marketing.models import SocialProfileSettings


class OrderActionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "product-order-action" in attributes.get("class", "").split():
            self.links.append(attributes)


@override_settings(PUBLIC_BASE_URL="https://leosoftug.com")
class ProductOrderLinkTests(SimpleTestCase):
    def setUp(self):
        self.product = SimpleNamespace(
            name='HP EliteBook & SSD "Plus" – 16GB',
            kind=Product.KIND_PHYSICAL,
            get_absolute_url=lambda: "/catalog/p/hp-elitebook-plus/",
        )
        self.context = {
            "company": SimpleNamespace(company_name="Leosoft UG", phone="0706 488 229"),
            "social_profiles": SimpleNamespace(whatsapp_number="+256 (706) 488-229"),
        }

    def test_order_links_normalize_numbers_and_encode_product_context(self):
        links = product_order_links(self.context, self.product)

        self.assertEqual(links["call_url"], "tel:+256706488229")
        url = urlsplit(links["whatsapp_url"])
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "wa.me", "/256706488229"))
        message = parse_qs(url.query)["text"][0]
        self.assertIn(f"order {self.product.name}", message)
        self.assertIn("https://leosoftug.com/catalog/p/hp-elitebook-plus/", message)
        self.assertEqual(set(parse_qs(url.query)), {"text"})

    def test_service_message_requests_a_booking(self):
        self.product.kind = Product.KIND_SERVICE
        message = parse_qs(urlsplit(product_order_links(self.context, self.product)["whatsapp_url"]).query)["text"][0]

        self.assertIn(f"book {self.product.name}", message)

    def test_missing_whatsapp_does_not_assume_the_call_number_is_on_whatsapp(self):
        self.context["social_profiles"].whatsapp_number = ""
        links = product_order_links(self.context, self.product)

        self.assertEqual(links, {"call_url": "tel:+256706488229", "whatsapp_url": ""})

    def test_unconfigured_numbers_do_not_render_dead_ordering_buttons(self):
        self.context["company"].phone = ""
        self.context["social_profiles"].whatsapp_number = ""
        html = render_to_string(
            "catalog/_product_order_actions.html", {**self.context, "p": self.product}
        )

        self.assertEqual(html.strip(), "")


class ProductOrderingJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Laptops", slug="ordering-laptops")
        cls.product = Product.objects.create(
            category=category,
            name="Order Context Laptop",
            slug="order-context-laptop",
            price=Decimal("850000.00"),
            stock_quantity=2,
            is_published=True,
            is_featured=False,
        )
        company = CompanySettings.load()
        company.phone = "0706 488 229"
        company.save(update_fields=["phone"])
        profiles = SocialProfileSettings.load()
        profiles.whatsapp_number = "0706 488 229"
        profiles.save(update_fields=["whatsapp_number"])

    def test_homepage_shows_products_before_discovery_copy_without_featured_flags(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#homepage-products"')
        self.assertLess(html.index('id="homepage-products"'), html.index('id="homepage-discovery"'))
        self.assertLess(html.index(self.product.name), html.index('id="homepage-discovery"'))
        self.assertNotContains(response, "What are you looking for today?")
        self.assertEqual([p.pk for p in response.context["featured_products"]], [self.product.pk])

    def test_cards_and_purchase_panel_offer_the_correct_ordering_links(self):
        for path in [reverse("home"), reverse("physical_product_list"), self.product.get_absolute_url()]:
            with self.subTest(path=path):
                response = self.client.get(path)
                parser = OrderActionParser()
                parser.feed(response.content.decode())
                self.assertEqual(response.status_code, 200)
                calls = [link for link in parser.links if link["href"].startswith("tel:")]
                chats = [link for link in parser.links if link["href"].startswith("https://wa.me/")]
                self.assertTrue(calls)
                self.assertEqual(len(calls), len(chats))
                for call in calls:
                    self.assertEqual(call["href"], "tel:+256706488229")
                    self.assertIn(self.product.name, call["aria-label"])
                for chat in chats:
                    message = parse_qs(urlsplit(chat["href"]).query)["text"][0]
                    self.assertIn(self.product.name, message)
                    self.assertIn(self.product.get_absolute_url(), message)
                    self.assertIn("noopener", chat["rel"])

    def test_out_of_stock_products_keep_contact_ordering_available(self):
        self.product.stock_quantity = 0
        self.product.save(update_fields=["stock_quantity"])
        response = self.client.get(self.product.get_absolute_url())

        self.assertContains(response, "Ask about availability")
        self.assertContains(response, 'class="product-order-action product-order-action--call"')
        self.assertContains(response, 'class="product-order-action product-order-action--whatsapp"')

    def test_order_actions_use_loaded_settings_without_per_product_queries(self):
        context = {
            "p": self.product,
            "company": CompanySettings.load(),
            "social_profiles": SocialProfileSettings.load(),
        }
        with self.assertNumQueries(0):
            html = render_to_string("catalog/_product_order_actions.html", context)

        self.assertIn("tel:+256706488229", html)
