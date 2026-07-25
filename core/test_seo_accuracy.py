import tempfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from catalog.seo_feeds import GOOGLE_NS
from growth.models import GrowthSettings

TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="leosoft-seo-accuracy-"))


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    PUBLIC_BASE_URL="https://leosoftug.com",
)
class SEOAccuracyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        growth = GrowthSettings.load()
        growth.merchant_return_policy_url = "https://leosoftug.com/returns/"
        growth.merchant_country = "UG"
        growth.merchant_shipping_service = "Standard delivery"
        growth.merchant_shipping_price = Decimal("10000")
        growth.save()

        category = Category.objects.create(
            name="Accessories",
            slug="seo-accuracy-accessories",
            description="Computer accessories and compatible equipment.",
        )
        cls.product = Product.objects.create(
            category=category,
            kind=Product.KIND_PHYSICAL,
            name="Generic USB-C Adapter",
            slug="generic-usb-c-adapter-seo-accuracy",
            sku="INTERNAL-SKU-ONLY",
            short_description="A practical USB-C adapter with an internal stock code.",
            description=(
                "This adapter is recorded with a merchant SKU but has no manufacturer "
                "GTIN, brand or MPN assigned in the catalogue."
            ),
            price=Decimal("75000"),
            stock_quantity=2,
            is_published=True,
            image=SimpleUploadedFile(
                "generic-usb-c-adapter.jpg",
                b"seo-accuracy-image",
                content_type="image/jpeg",
            ),
        )

    def test_internal_sku_does_not_become_a_global_identifier(self):
        response = self.client.get(reverse("google_merchant_feed"))
        root = ET.fromstring(response.content)
        namespace = {"g": GOOGLE_NS}
        target = None
        for item in root.findall("./channel/item"):
            item_id = item.find("g:id", namespace)
            if item_id is not None and item_id.text == self.product.sku:
                target = item
                break

        self.assertIsNotNone(target)
        identifier = target.find("g:identifier_exists", namespace)
        self.assertIsNotNone(identifier)
        self.assertEqual(identifier.text, "no")

    def test_return_policy_url_alone_is_not_published_as_complete_offer_policy(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "hasMerchantReturnPolicy")
        self.assertNotContains(response, "MerchantReturnPolicy")
