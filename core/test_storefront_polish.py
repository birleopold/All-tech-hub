from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, ProductImage, ProductVariant
from commerce.cart import CART_SESSION_KEY, iter_cart_lines
from commerce.models import Order
from core.models import CompanySettings
from crm.models import Customer
from marketing.models import SocialProfileSettings
from merchandising.models import ProductCommerceProfile


class StorefrontPolishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CompanySettings.objects.update_or_create(
            pk=1,
            defaults={
                "company_name": "LEOSOFT UG LTD",
                "phone": "+256 700 123456",
                "address_line": "Test location",
                "city": "Kampala",
            },
        )
        SocialProfileSettings.objects.update_or_create(
            pk=1, defaults={"whatsapp_number": "256700123456"}
        )
        cls.category = Category.objects.create(name="Work laptops", slug="work-laptops")
        cls.product = Product.objects.create(
            category=cls.category,
            name="Business notebook",
            slug="business-notebook",
            price=Decimal("850000"),
            stock_quantity=10,
            description="A portable computer for everyday work.",
        )
        ProductImage.objects.create(product=cls.product, image="", sort_order=0)
        ProductImage.objects.create(
            product=cls.product,
            image="products/gallery/notebook-front.jpg",
            sort_order=2,
        )
        ProductImage.objects.create(
            product=cls.product,
            image="products/gallery/notebook-side.jpg",
            sort_order=4,
        )
        ProductCommerceProfile.objects.create(
            product=cls.product,
            processor_family="Intel Core i5",
            ram_capacity="16 GB",
        )
        cls.service = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_SERVICE,
            name="Network installation",
            slug="network-installation",
            price=Decimal("0"),
            short_description="Plan a network for your workplace.",
        )
        cls.user = get_user_model().objects.create_user(
            username="storefront-customer", password="test-only-password"
        )
        cls.customer = Customer.objects.create(name="Amina", user=cls.user)
        cls.order = Order.objects.create(
            reference="ORD-POLISH-OWN",
            customer=cls.customer,
            contact_name=cls.customer.name,
            status=Order.STATUS_DISPATCHED,
        )
        other_customer = Customer.objects.create(name="Other customer")
        cls.other_order = Order.objects.create(
            reference="ORD-POLISH-PRIVATE",
            customer=other_customer,
            contact_name=other_customer.name,
        )

    def test_buying_controls_precede_specifications_and_description(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(html.index('id="pd-main-wrap"'), html.index('id="product-buy-panel"'))
        self.assertLess(
            html.index('id="product-buy-panel"'),
            html.index('id="verified-specifications-heading"'),
        )
        self.assertLess(
            html.index('id="verified-specifications-heading"'), html.index('id="overview"')
        )
        self.assertContains(response, "16 GB")
        self.assertContains(response, "Intel Core i5")
        self.assertContains(response, reverse("cart_add", args=[self.product.pk]))

    def test_unpriced_service_invites_scope_confirmation(self):
        response = self.client.get(self.service.get_absolute_url())
        self.assertContains(response, "Request an estimate")
        self.assertContains(response, "Tell us the scope and location")
        self.assertContains(response, "Confirm the scope")
        self.assertContains(response, "type=support&amp;product=network-installation")
        self.assertNotContains(response, "UGX 0</")

    def test_service_catalogue_preserves_search_and_booking_links(self):
        response = self.client.get(reverse("service_list"), {"q": "Network"})
        self.assertContains(response, self.service.name)
        self.assertContains(response, "Request an estimate")
        self.assertContains(response, self.service.get_absolute_url())
        self.assertNotContains(response, self.product.get_absolute_url())

    def test_about_gallery_uses_published_product_photos_only(self):
        Product.objects.create(
            category=self.category,
            name="Private draft notebook",
            slug="private-draft-notebook",
            price=Decimal("1"),
            image="products/private-draft.jpg",
            is_published=False,
        )
        response = self.client.get(reverse("about"))
        self.assertContains(response, "notebook-front.jpg")
        self.assertContains(response, self.product.get_absolute_url())
        self.assertNotContains(response, "private-draft.jpg")
        self.assertNotContains(response, "Private draft notebook")
        self.assertEqual(len(response.context["about_products"]), 1)

    def test_about_remains_useful_without_catalogue_photos(self):
        ProductImage.objects.all().delete()
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="about-photo-grid"')
        self.assertContains(response, reverse("service_list"))
        self.assertContains(response, "Contact Leosoft")

    def test_contact_direct_actions_precede_request_form(self):
        response = self.client.get(reverse("contact"))
        html = response.content.decode()
        shortcut_start = html.index('class="contact-shortcuts"')
        form_start = html.index('id="contact-form"')
        shortcuts = html[shortcut_start:form_start]
        self.assertIn('href="tel:+256700123456"', shortcuts)
        self.assertIn('href="https://wa.me/256700123456"', shortcuts)
        self.assertIn("maps/search/?api=1", shortcuts)
        self.assertIn('rel="noopener noreferrer"', shortcuts)

    def test_contact_invalid_submission_keeps_linked_product_and_errors(self):
        response = self.client.post(
            reverse("contact"),
            {"product": self.product.slug, "request_type": "quote", "name": "Amina"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, self.product.name)
        self.assertEqual(response.context["contact_product"], self.product)

    def test_gallery_fallback_skips_blank_images_and_uses_first_sort_order(self):
        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(
            product.primary_display_image.name, "products/gallery/notebook-front.jpg"
        )

    def test_prefetched_gallery_can_supply_cart_thumbnail_without_queries(self):
        lines = list(iter_cart_lines({CART_SESSION_KEY: {f"p:{self.product.pk}": 2}}))
        self.assertEqual(len(lines), 1)
        with self.assertNumQueries(0):
            self.assertEqual(
                lines[0].product.primary_display_image.name,
                "products/gallery/notebook-front.jpg",
            )

    def test_primary_image_precedes_prefetched_gallery(self):
        Product.objects.filter(pk=self.product.pk).update(image="products/main.jpg")
        product = Product.objects.prefetch_related("gallery_images").get(pk=self.product.pk)
        with self.assertNumQueries(0):
            self.assertEqual(product.primary_display_image.name, "products/main.jpg")

    def test_cart_and_checkout_preserve_variant_quantity_and_totals(self):
        variant = ProductVariant.objects.create(
            product=self.product, name="16 GB / Silver", price=Decimal("900000"),
            stock_quantity=5,
        )
        session = self.client.session
        session[CART_SESSION_KEY] = {f"v:{variant.pk}": 1}
        session.save()
        response = self.client.get(reverse("cart"))
        self.assertContains(response, "notebook-front.jpg")
        self.assertContains(response, f'name="qty_v_{variant.pk}"')
        self.client.post(reverse("cart_update"), {f"qty_v_{variant.pk}": "2"})
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, "notebook-front.jpg")
        self.assertContains(response, "16 GB / Silver")
        self.assertContains(response, 'name="checkout_token"')
        self.assertEqual(response.context["subtotal"], Decimal("1800000"))
        self.assertEqual(response.context["checkout_lines"][0]["qty"], 2)

    def test_account_navigation_and_orders_are_customer_scoped(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("portal_orders"))
        self.assertContains(response, "Customer account navigation")
        self.assertContains(response, f'href="{reverse("portal_orders")}" aria-current="page"')
        self.assertContains(response, self.order.reference)
        self.assertContains(response, "Dispatched")
        self.assertNotContains(response, self.other_order.reference)
        response = self.client.get(reverse("portal_order_detail", args=[self.other_order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_account_navigation_is_absent_from_anonymous_login(self):
        response = self.client.get(reverse("portal_login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Customer account navigation")

    def test_secondary_customer_pages_render_with_shared_navigation(self):
        self.client.force_login(self.user)
        for name in (
            "portal_home", "portal_jobs", "portal_documents", "portal_warranties",
            "portal_tickets", "portal_wishlist", "portal_addresses",
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Customer account navigation")
