"""Uganda category SEO: exact titles, short customer copy and safe overrides."""
from django.test import TestCase, override_settings
from django.utils.html import escape
from django.urls import reverse

from catalog.local_seo import CATEGORY_SEARCH_COPY, category_metadata
from catalog.models import Category, Product
from core.seo import meta_description


@override_settings(
    SECURE_SSL_REDIRECT=False,
    PUBLIC_BASE_URL="https://leosoftug.com",
)
class UgandaCategorySEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.categories = []
        for index, (name, slug) in enumerate((
            ("Laptops", "laptops"),
            ("Desktop Computers", "desktop-computers"),
            ("Networking Equipment", "networking-equipment"),
            ("Printers, Scanners and Supplies", "printers-scanners-supplies"),
            ("Storage Devices", "storage-devices"),
            ("Computer Accessories", "computer-accessories"),
        )):
            category = Category.objects.create(
                name=name, slug=slug, sort_order=index,
                description="An introduction to the category. " * 36,
            )
            Product.objects.create(
                name=f"Test product for {name}",
                slug=f"seo-ug-category-item-{index}",
                category=category,
                price="85000.00",
                stock_quantity=1,
                is_published=True,
            )
            cls.categories.append(category)

    def test_all_six_departments_render_unique_keyword_titles_and_snippets(self):
        titles = set()
        descriptions = set()
        for category in self.categories:
            with self.subTest(category=category.slug):
                copy = category_metadata(category)
                path = reverse("product_category", args=[category.slug])
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"<title>{escape(copy.title)}</title>", html=False)
                self.assertContains(
                    response,
                    f'<meta name="description" content="{meta_description(copy.description)}">',
                    html=False,
                )
                self.assertContains(response, copy.heading)
                self.assertContains(
                    response,
                    f'<link rel="canonical" href="https://leosoftug.com{path}">',
                    html=False,
                )
                self.assertContains(response, 'content="index,follow', html=False)
                self.assertLessEqual(len(copy.title), 75)
                self.assertLessEqual(len(meta_description(copy.description)), 160)
                self.assertLessEqual(len(response.context["catalog_intro"].split()), 20)
                titles.add(copy.title)
                descriptions.add(copy.description)
        self.assertEqual(len(titles), 6)
        self.assertEqual(len(descriptions), 6)

    def test_staff_can_override_each_seo_field_without_changing_slug(self):
        laptops = self.categories[0]
        url = reverse("product_category", args=[laptops.slug])
        laptops.seo_title = "Student Laptops Kampala | Leosoft UG"
        laptops.seo_description = "Compare selected student laptops at LEOSOFT."
        laptops.seo_heading = "Laptops for Students in Kampala"
        laptops.save()
        response = self.client.get(url)
        self.assertContains(response, "<title>Student Laptops Kampala | Leosoft UG</title>", html=False)
        self.assertContains(response, 'content="Compare selected student laptops at LEOSOFT."', html=False)
        self.assertContains(response, "<h1", html=False)
        self.assertContains(response, laptops.seo_heading)
        self.assertEqual(response.context["catalog_canonical_url"], f"https://leosoftug.com{url}")

    def test_staff_seo_dashboard_lists_category_preview_and_edit_controls(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        editor = get_user_model().objects.create_user(
            username="ug-seo-category-editor", password="pw", is_staff=True,
        )
        editor.user_permissions.add(
            Permission.objects.get(
                codename="change_category", content_type__app_label="catalog",
            )
        )
        self.client.force_login(editor)
        response = self.client.get(reverse("staff_seo"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uganda category search previews")
        self.assertContains(response, CATEGORY_SEARCH_COPY["laptops"].title)
        self.assertContains(response, "Edit SEO")
        self.assertContains(response, "Google Business Profile and free product listings")

    def test_unknown_category_gets_safe_specific_default_not_duplicate_title(self):
        unknown = Category.objects.create(name="Smart Home Devices", slug="smart-home-devices")
        copy = category_metadata(unknown)
        self.assertIn("Smart Home Devices", copy.title)
        self.assertIn("Leosoft UG", copy.title)
        self.assertNotIn("fast delivery", copy.description.lower())

    def test_query_filters_stay_noindex_even_after_category_metadata_is_added(self):
        response = self.client.get(
            reverse("product_category", args=[self.categories[0].slug]),
            {"sort": "price_low", "min_price": "20000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'content="noindex,follow', html=False)

    def test_category_seo_never_fabricates_stock_brand_counts_or_five_star_claims(self):
        for copy in CATEGORY_SEARCH_COPY.values():
            text = f"{copy.title} {copy.description}".lower()
            for forbidden in (
                "50+", "54 items", "original", "5-star", "fast delivery",
                "best prices", "in stock now", "guaranteed",
            ):
                self.assertNotIn(forbidden, text)
