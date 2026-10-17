import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from core.models import CompanySettings
from growth.models import GrowthSettings, ProductGrowthData

TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="leosoft-seo-tests-"))


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    PUBLIC_BASE_URL="https://leosoftug.com",
    SEO_DEFAULT_TITLE="LEOSOFT UG LTD — Computers and IT support in Uganda",
    SEO_DEFAULT_DESCRIPTION="Shop computers and request professional IT support in Uganda.",
    BING_SITE_VERIFICATION_TOKEN="bing-verification-token",
    INDEXNOW_KEY="indexnow-test-key-1234567890",
)
class GlobalSEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = CompanySettings.load()
        company.company_name = "LEOSOFT UG LTD"
        company.legal_name = "LEOSOFT UG LTD"
        company.website = "https://leosoftug.com"
        company.phone = "+256 700 000000"
        company.email = "sales@leosoftug.com"
        company.address_line = "Kampala Road"
        company.city = "Kampala"
        company.country = "Uganda"
        company.save()

        growth = GrowthSettings.load()
        growth.search_console_verification_token = "google-verification-token"
        growth.merchant_country = "UG"
        growth.merchant_language = "en"
        growth.merchant_shipping_service = "Standard delivery"
        growth.merchant_shipping_price = Decimal("10000")
        growth.merchant_return_policy_url = "https://leosoftug.com/returns/"
        growth.save()

        cls.category = Category.objects.create(
            name="Laptops",
            slug="laptops",
            description="Compare laptops for school, business and professional work.",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="HP ProBook SEO Test",
            slug="hp-probook-seo-test",
            sku="HP-SEO-001",
            short_description="A dependable HP business laptop for work and learning.",
            description=(
                "This HP ProBook combines practical business performance, portable design "
                "and clear configuration options for customers in Uganda."
            ),
            price=Decimal("1500000"),
            stock_quantity=3,
            is_published=True,
            image=SimpleUploadedFile(
                "hp-probook-seo.jpg",
                b"seo-test-image-bytes",
                content_type="image/jpeg",
            ),
        )
        ProductGrowthData.objects.create(
            product=cls.product,
            brand="HP",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
            gtin="1234567890123",
            mpn="PROBOOK-SEO",
            google_product_category="Electronics > Computers > Laptops",
            custom_label_0="business-laptop",
        )
        cls.variant_one = ProductVariant.objects.create(
            product=cls.product,
            name="16GB RAM / 512GB SSD",
            sku="HP-SEO-16-512",
            price=Decimal("1700000"),
            stock_quantity=2,
        )
        cls.variant_two = ProductVariant.objects.create(
            product=cls.product,
            name="8GB RAM / 256GB SSD",
            sku="HP-SEO-8-256",
            price=Decimal("1500000"),
            stock_quantity=0,
        )
        cls.service = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_SERVICE,
            name="Laptop diagnostics",
            slug="laptop-diagnostics-seo-test",
            short_description="Professional laptop diagnostics and fault assessment.",
            description="A structured diagnostic service for laptop hardware and software faults.",
            price=Decimal("50000"),
            is_published=True,
        )
        cls.staff = get_user_model().objects.create_user(
            username="seo-staff",
            password="seo-test-password",
            is_staff=True,
        )

    def test_home_uses_canonical_origin_without_tracking_query(self):
        response = self.client.get("/?utm_source=test&utm_campaign=seo")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="canonical" href="https://leosoftug.com/">',
            html=False,
        )
        self.assertNotContains(response, "utm_source=test")
        self.assertContains(response, "google-verification-token")
        self.assertContains(response, "bing-verification-token")
        self.assertContains(response, 'lang="en-UG"', html=False)

    def test_clean_category_collection_brand_and_service_landings_are_indexable(self):
        cases = (
            (reverse("product_category", args=[self.category.slug]), "Laptops in Uganda"),
            (reverse("product_collection", args=["business"]), "For business"),
            (reverse("product_brand", args=["hp"]), "HP computers"),
            (reverse("physical_product_list"), "Computers and technology products"),
            (reverse("service_list"), "Computer repairs and IT services"),
        )
        for path, title_fragment in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title_fragment)
                self.assertContains(
                    response,
                    f'<link rel="canonical" href="https://leosoftug.com{path}">',
                    html=False,
                )
                self.assertContains(response, 'content="index,follow', html=False)

    def test_search_and_filtered_catalogue_pages_are_noindex(self):
        search = self.client.get(reverse("product_list"), {"q": "HP"})
        filtered = self.client.get(
            reverse("product_category", args=[self.category.slug]),
            {"min_price": "1000000", "sort": "price_low"},
        )

        self.assertContains(search, 'content="noindex,follow', html=False)
        self.assertContains(filtered, 'content="noindex,follow', html=False)
        self.assertContains(
            filtered,
            '<link rel="canonical" href="https://leosoftug.com/catalog/category/laptops/">',
            html=False,
        )

    def test_product_detail_uses_product_group_schema_for_variants(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type":"ProductGroup"', html=False)
        self.assertContains(response, '"hasVariant"', html=False)
        self.assertContains(response, self.variant_one.sku)
        self.assertContains(response, self.variant_two.sku)
        self.assertContains(
            response,
            f'<link rel="canonical" href="https://leosoftug.com{self.product.get_absolute_url()}">',
            html=False,
        )
        self.assertContains(response, 'product:availability', html=False)

    def test_sitemap_index_and_sections_use_canonical_urls(self):
        index = self.client.get(reverse("sitemap_index"))
        products = self.client.get(reverse("seo_sitemap", args=["products"]))
        categories = self.client.get(reverse("seo_sitemap", args=["categories"]))
        legacy = reverse("django.contrib.sitemaps.views.sitemap")

        self.assertEqual(index.status_code, 200)
        ET.fromstring(index.content)
        self.assertContains(index, "https://leosoftug.com/sitemaps/products.xml")
        self.assertContains(index, "https://leosoftug.com/image-sitemap.xml")
        self.assertContains(products, f"https://leosoftug.com{self.product.get_absolute_url()}")
        self.assertContains(categories, "https://leosoftug.com/catalog/category/laptops/")
        self.assertEqual(legacy, "/sitemap.xml")

    def test_image_sitemap_exposes_product_image(self):
        response = self.client.get(reverse("image_sitemap"))

        self.assertEqual(response.status_code, 200)
        ET.fromstring(response.content)
        self.assertContains(response, "hp-probook-seo")
        self.assertContains(response, "https://leosoftug.com/media/")

    def test_merchant_feed_contains_physical_variants_and_excludes_service(self):
        response = self.client.get(reverse("google_merchant_feed"))

        self.assertEqual(response.status_code, 200)
        ET.fromstring(response.content)
        self.assertContains(response, self.variant_one.sku)
        self.assertContains(response, self.variant_two.sku)
        self.assertContains(response, "item_group_id")
        self.assertContains(response, "1700000.00 UGX")
        self.assertNotContains(response, self.service.name)
        self.assertEqual(
            response["X-Robots-Tag"],
            "noindex, nofollow, noarchive",
        )

    def test_robots_references_canonical_sitemaps_and_blocks_private_workspaces(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sitemap: https://leosoftug.com/sitemap.xml")
        self.assertContains(response, "Sitemap: https://leosoftug.com/image-sitemap.xml")
        self.assertContains(response, "Disallow: /staff/")
        self.assertContains(response, "Disallow: /admin/")

    def test_indexnow_key_and_dry_run_are_available(self):
        response = self.client.get(reverse("indexnow_key"))
        output = StringIO()
        call_command(
            "submit_indexnow",
            self.product.get_absolute_url(),
            "--dry-run",
            stdout=output,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().strip(), "indexnow-test-key-1234567890")
        # The command writes a JSON object followed by a human-readable
        # completion line; decode the first complete JSON value.
        payload, _offset = json.JSONDecoder().raw_decode(output.getvalue())
        self.assertEqual(payload["host"], "leosoftug.com")
        self.assertIn(
            f"https://leosoftug.com{self.product.get_absolute_url()}",
            payload["urlList"],
        )

    def test_contact_query_parameters_do_not_change_canonical(self):
        response = self.client.get(
            reverse("contact"),
            {"type": "quote", "product": self.product.slug, "utm_source": "test"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="canonical" href="https://leosoftug.com/contact/">',
            html=False,
        )

    def test_staff_has_an_owner_facing_seo_control_center(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_seo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEO, Merchant and search opportunities")
        self.assertContains(response, "https://leosoftug.com/sitemap.xml")
        self.assertContains(response, "Google Search Console verification is configured")

    def test_seo_audit_command_runs(self):
        output = StringIO()
        call_command("audit_seo", stdout=output)
        self.assertIn("SEO readiness", output.getvalue())
        self.assertIn("sitemap_index", output.getvalue().lower())
