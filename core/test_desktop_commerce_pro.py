from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from commerce.forms import CheckoutForm


@override_settings(PUBLIC_BASE_URL="https://leosoftug.com")
class DesktopCommerceProTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Desktop Commerce Laptops",
            slug="desktop-commerce-laptops",
            description="Laptops used to verify the desktop catalogue experience.",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Desktop Commerce Test Laptop",
            slug="desktop-commerce-test-laptop",
            short_description="A published laptop used for desktop interface testing.",
            description="A detailed laptop description for desktop catalogue regression coverage.",
            price=Decimal("1500000"),
            stock_quantity=2,
            track_inventory=True,
            is_published=True,
        )

    def test_home_exposes_desktop_search_discovery_and_assets(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/desktop_commerce_pro.css")
        self.assertContains(response, "js/desktop_commerce_pro.js")
        self.assertContains(response, "data-desktop-search-form")
        self.assertContains(response, "data-desktop-search-discovery")
        self.assertContains(response, "data-desktop-recent-searches")
        self.assertContains(response, "Control+K Meta+K /")
        self.assertContains(response, "Popular destinations")

    def test_catalogue_exposes_sticky_controls_compact_view_and_labels(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-desktop-catalog-control")
        self.assertContains(response, 'data-market-view="compact"', html=False)
        self.assertContains(response, "Compact grid")
        self.assertContains(response, "Desktop Commerce Test Laptop")
        self.assertContains(response, '<span class="desktop-action-label">Quick view</span>', html=False)
        self.assertContains(response, '<span class="desktop-action-label">Add</span>', html=False)
        self.assertContains(response, '<span class="desktop-action-label">Compare</span>', html=False)
        self.assertContains(response, '<span class="desktop-action-label">Save</span>', html=False)

    def test_desktop_assets_include_search_sticky_density_and_reduced_motion(self):
        css = (
            Path(settings.BASE_DIR) / "static" / "css" / "desktop_commerce_pro.css"
        ).read_text(encoding="utf-8")
        javascript = (
            Path(settings.BASE_DIR) / "static" / "js" / "desktop_commerce_pro.js"
        ).read_text(encoding="utf-8")

        self.assertIn("@media (min-width: 1200px)", css)
        self.assertIn(".desktop-search-discovery", css)
        self.assertIn(".desktop-catalog-control-deck", css)
        self.assertIn(".market-catalog-grid.is-compact", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("leosoft-desktop-recent-searches", javascript)
        self.assertIn("supportedViews", javascript)
        self.assertIn("is-stuck", javascript)

    def test_checkout_form_exposes_autofill_and_keyboard_hints(self):
        form = CheckoutForm()

        self.assertEqual(form.fields["name"].widget.attrs["autocomplete"], "name")
        self.assertEqual(form.fields["email"].widget.attrs["autocomplete"], "email")
        self.assertEqual(form.fields["phone"].widget.attrs["autocomplete"], "tel")
        self.assertEqual(form.fields["phone"].widget.attrs["inputmode"], "tel")
        self.assertEqual(
            form.fields["billing_address"].widget.attrs["autocomplete"],
            "billing street-address",
        )
        self.assertEqual(
            form.fields["shipping_address"].widget.attrs["autocomplete"],
            "shipping street-address",
        )

    def test_cart_and_checkout_templates_keep_desktop_progress_and_confidence(self):
        templates = Path(settings.BASE_DIR) / "templates" / "commerce"
        cart = (templates / "cart.html").read_text(encoding="utf-8")
        checkout = (templates / "checkout.html").read_text(encoding="utf-8")

        self.assertIn("desktop-checkout-progress", cart)
        self.assertIn("desktop-cart-table", cart)
        self.assertIn("desktop-cart-summary", cart)
        self.assertIn("desktop-order-confidence", cart)
        self.assertIn("desktop-checkout-progress", checkout)
        self.assertIn("desktop-checkout-fields", checkout)
        self.assertIn("desktop-checkout-field--{{ field.name }}", checkout)
        self.assertIn("Edit cart", checkout)
