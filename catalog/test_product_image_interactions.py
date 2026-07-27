import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from catalog.models import Category, Product, ProductImage

TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="leosoft-product-motion-"))
ONE_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
    b"\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    PUBLIC_BASE_URL="https://leosoftug.com",
)
class ProductImageInteractionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(
            name="Animated Product Test",
            slug="animated-product-test",
            description="Products used to verify public image interactions.",
        )
        cls.product = Product.objects.create(
            category=category,
            kind=Product.KIND_PHYSICAL,
            name="Animated Gallery Laptop",
            slug="animated-gallery-laptop",
            short_description="A laptop with multiple customer-visible images.",
            description="A detailed test product for gallery and quick-view behavior.",
            price=Decimal("1500000"),
            stock_quantity=2,
            is_published=True,
        )
        ProductImage.objects.create(
            product=cls.product,
            image=SimpleUploadedFile(
                "animated-gallery-front.gif",
                ONE_PIXEL_GIF,
                content_type="image/gif",
            ),
            alt_text="Animated Gallery Laptop front view",
            sort_order=1,
        )
        ProductImage.objects.create(
            product=cls.product,
            image=SimpleUploadedFile(
                "animated-gallery-side.gif",
                ONE_PIXEL_GIF,
                content_type="image/gif",
            ),
            alt_text="Animated Gallery Laptop side view",
            sort_order=2,
        )

    def test_product_detail_exposes_multiple_gallery_thumbnails(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "product-gallery-thumbs")
        self.assertContains(response, 'class="pd-thumb"', count=2)
        self.assertContains(response, "Animated Gallery Laptop front view")
        self.assertContains(response, "Animated Gallery Laptop side view")

    def test_catalogue_card_keeps_quick_view_content(self):
        response = self.client.get("/catalog/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "market-card-quick-view")
        self.assertContains(response, "market-card-quick-view__panel")
        self.assertContains(response, self.product.name)

    def test_interaction_assets_include_navigation_motion_and_overflow_guards(self):
        marketplace_js = Path("static/js/marketplace_experience.js").read_text(
            encoding="utf-8"
        )
        detail_js = Path("static/js/public_detail_contact.js").read_text(
            encoding="utf-8"
        )
        interaction_css = Path(
            "static/css/search_conversion_refinement.css"
        ).read_text(encoding="utf-8")

        self.assertIn("market-quick-view-open", marketplace_js)
        self.assertIn("data-market-quick-view-close", marketplace_js)
        self.assertIn("product-gallery-nav--previous", detail_js)
        self.assertIn('event.key === "ArrowLeft"', detail_js)
        self.assertIn('"touchstart"', detail_js)
        self.assertIn("overflow-wrap: anywhere", interaction_css)
        self.assertIn("product-gallery-stage.is-pointer-active", interaction_css)
        self.assertIn("position: fixed !important", interaction_css)
