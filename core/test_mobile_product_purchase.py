"""Mobile product purchases must mirror real product availability and variant price."""
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductImage, ProductVariant


@override_settings(SECURE_SSL_REDIRECT=False)
class MobileProductPurchaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Laptop computers", slug="mobile-shop-laptops",
        )
        cls.physical = Product.objects.create(
            category=cls.category, name="Office laptop", slug="mobile-office-laptop",
            price=Decimal("850000"), stock_quantity=3, is_published=True,
        )
        cls.with_variants = Product.objects.create(
            category=cls.category, name="Laptop configurations",
            slug="mobile-configuration-laptop", price=Decimal("950000"),
            stock_quantity=0, is_published=True,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.with_variants, name="16GB RAM / 512GB SSD",
            price=Decimal("1250000"), stock_quantity=2, is_active=True,
        )
        cls.unavailable = Product.objects.create(
            category=cls.category, name="Unavailable laptop",
            slug="mobile-unavailable-laptop", price=Decimal("890000"),
            stock_quantity=0, is_published=True,
        )
        cls.quote_service = Product.objects.create(
            category=cls.category, name="Repair quotation",
            slug="mobile-repair-quotation", kind=Product.KIND_SERVICE,
            price=0, track_inventory=False, is_published=True,
        )
        cls.priced_service = Product.objects.create(
            category=cls.category, name="Laptop cleanup",
            slug="mobile-laptop-cleanup", kind=Product.KIND_SERVICE,
            price=Decimal("75000"), track_inventory=False, is_published=True,
        )

    def test_in_stock_physical_mobile_cta_submits_existing_cart_form(self):
        response = self.client.get(self.physical.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="product-cart-form"')
        self.assertContains(response, 'type="submit" form="product-cart-form"')
        self.assertContains(response, 'data-mobile-product-price')
        self.assertContains(response, "Add to cart")
        self.assertContains(response, "Available to order")
        self.assertNotContains(response, "Available now</span>")

    def test_variant_mobile_cta_requires_selection_and_carries_exact_price(self):
        response = self.client.get(self.with_variants.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-mobile-variant-action')
        self.assertContains(response, 'href="#variant_id"')
        self.assertContains(response, 'data-price="1250000.00"')
        self.assertContains(response, 'id="product-cart-form"')
        self.assertContains(response, "Choose option")
        self.assertNotContains(response, 'type="submit" form="product-cart-form"')

    def test_unavailable_product_offers_enquiry_not_cart_submit(self):
        response = self.client.get(self.unavailable.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enquire")
        self.assertContains(response, "Contact the team to confirm availability")
        self.assertContains(response, "type=product")
        self.assertNotContains(response, 'id="product-cart-form"')

    def test_quote_only_service_does_not_offer_zero_price_cart_action(self):
        response = self.client.get(self.quote_service.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request quote")
        self.assertContains(response, "Request an estimate")
        self.assertNotContains(response, 'id="product-cart-form"')

    def test_priced_service_has_functional_mobile_cart_button(self):
        response = self.client.get(self.priced_service.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="product-cart-form"')
        self.assertContains(response, 'type="submit" form="product-cart-form"')
        self.assertContains(response, "Add service")

    def test_gallery_explains_swipe_without_overwhelming_purchasing(self):
        ProductImage.objects.create(
            product=self.physical, image="products/laptop-front.jpg",
            sort_order=0,
        )
        ProductImage.objects.create(
            product=self.physical, image="products/laptop-side.jpg",
            sort_order=1,
        )
        response = self.client.get(self.physical.get_absolute_url())
        self.assertContains(response, "Tap a photo or swipe the main image")
        self.assertContains(response, 'data-product-zoom')
        self.assertContains(response, 'id="product-gallery-dialog"')
        html = response.content.decode()
        self.assertLess(html.index('id="pd-main-wrap"'), html.index('id="product-buy-panel"'))

    def test_mobile_variant_script_updates_both_prices_without_skipping_form(self):
        source = Path("static/js/public_detail_contact.js").read_text(encoding="utf-8")
        self.assertIn('const syncSelectedVariant = () =>', source)
        self.assertIn("variantSelect.selectedOptions", source)
        self.assertIn("mobilePriceLabel.textContent = value || defaultMobilePrice", source)
        self.assertIn('productForm.requestSubmit', source)
        self.assertIn('mobileVariantAction?.addEventListener("click"', source)
