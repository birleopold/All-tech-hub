from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(PUBLIC_BASE_URL="https://leosoftug.com")
class MobileCommerceProTests(TestCase):
    def test_home_exposes_mobile_search_as_primary_navigation(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "css/mobile_commerce_pro.css")
        self.assertContains(response, "js/mobile_commerce_pro.js")
        self.assertContains(response, "data-mobile-search-open")
        self.assertContains(response, "data-mobile-search-sheet")
        self.assertContains(response, "data-mobile-recent-searches")
        self.assertContains(response, "Primary mobile navigation")
        self.assertContains(response, ">Search</span></button>", html=False)

    def test_catalogue_has_mobile_filter_sheet_controls(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "market-mobile-filter__sheet-head")
        self.assertContains(response, "data-mobile-filter-close")
        self.assertContains(response, 'aria-controls="mobile-market-filter-panel"', html=False)
        self.assertContains(response, 'aria-expanded="false"', html=False)

    def test_mobile_assets_include_safe_area_touch_and_sheet_rules(self):
        css = (
            Path(settings.BASE_DIR) / "static" / "css" / "mobile_commerce_pro.css"
        ).read_text(encoding="utf-8")
        javascript = (
            Path(settings.BASE_DIR) / "static" / "js" / "mobile_commerce_pro.js"
        ).read_text(encoding="utf-8")

        self.assertIn("env(safe-area-inset-bottom", css)
        self.assertIn("--mobile-commerce-touch: 3rem", css)
        self.assertIn(".mobile-commerce-sticky-cta", css)
        self.assertIn(".market-mobile-filter__body", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("leosoft-mobile-recent-searches", javascript)
        self.assertIn("back_forward", javascript)
        self.assertIn("Placing order", javascript)

    def test_cart_and_checkout_templates_keep_mobile_primary_actions(self):
        templates = Path(settings.BASE_DIR) / "templates" / "commerce"
        cart = (templates / "cart.html").read_text(encoding="utf-8")
        checkout = (templates / "checkout.html").read_text(encoding="utf-8")

        self.assertIn("mobile-cart-page", cart)
        self.assertIn("cart-table", cart)
        self.assertIn('data-label="Quantity"', cart)
        self.assertIn("mobile-commerce-sticky-cta", cart)
        self.assertIn("mobile-checkout-progress", checkout)
        self.assertIn("data-mobile-checkout-form", checkout)
        self.assertIn('form="checkout-form"', checkout)
        self.assertIn("mobile-commerce-sticky-cta", checkout)
