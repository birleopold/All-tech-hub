from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog.models import Category, Product
from catalog.responsive_images import existing_responsive_sources, variant_name


def uploaded_image(name="product.jpg", size=(800, 400)):
    output = BytesIO()
    Image.new("RGB", size, (45, 90, 135)).save(output, format="JPEG", quality=92)
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


class ResponsiveProductImageTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            PRODUCT_IMAGE_WATERMARK_ENABLED=False,
            PRODUCT_IMAGE_RESPONSIVE_ENABLED=True,
            PRODUCT_IMAGE_RESPONSIVE_WIDTHS=(320, 640, 960),
            PRODUCT_IMAGE_RESPONSIVE_QUALITY=82,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.category = Category.objects.create(name="Computers", slug="computers")

    def test_upload_generates_only_non_enlarged_proportional_webp_files(self):
        product = Product.objects.create(
            category=self.category,
            name="Responsive laptop",
            slug="responsive-laptop",
            price="1200000.00",
            image=uploaded_image(),
        )

        sources = existing_responsive_sources(product.image)
        self.assertEqual([width for width, _url in sources], [320, 640])
        self.assertFalse(product.image.storage.exists(variant_name(product.image.name, 960)))

        for width in (320, 640):
            path = Path(self.media_dir.name) / variant_name(product.image.name, width)
            self.assertTrue(path.exists())
            with Image.open(path) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (width, width // 2))

    def test_small_image_is_never_enlarged(self):
        product = Product.objects.create(
            category=self.category,
            name="Small image",
            slug="small-image",
            price="500000.00",
            image=uploaded_image("small.jpg", size=(200, 100)),
        )
        self.assertEqual(existing_responsive_sources(product.image), [])

    def test_template_tag_renders_srcset_dimensions_and_fallback(self):
        product = Product.objects.create(
            category=self.category,
            name="Template image",
            slug="template-image",
            price="700000.00",
            image=uploaded_image("template.jpg"),
        )
        rendered = Template(
            "{% load catalog_images %}"
            "{% responsive_image image 'Laptop front view' 'img-fluid' '50vw' 'lazy' 'low' %}"
        ).render(Context({"image": product.image}))

        self.assertIn("<picture>", rendered)
        self.assertIn('type="image/webp"', rendered)
        self.assertIn("320w", rendered)
        self.assertIn("640w", rendered)
        self.assertIn('alt="Laptop front view"', rendered)
        self.assertIn('width="800"', rendered)
        self.assertIn('height="400"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn(product.image.url, rendered)

    def test_homepage_featured_products_use_responsive_picture_markup(self):
        Product.objects.create(
            category=self.category,
            name="Featured responsive laptop",
            slug="featured-responsive-laptop",
            price="900000.00",
            image=uploaded_image("featured.jpg"),
            is_featured=True,
        )
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Featured responsive laptop")
        self.assertContains(response, 'type="image/webp"')
        self.assertContains(response, "320w")

    def test_replacing_and_deleting_image_cleans_public_originals_and_derivatives(self):
        product = Product.objects.create(
            category=self.category,
            name="Replace image",
            slug="replace-image",
            price="950000.00",
            image=uploaded_image("old.jpg"),
        )
        old_name = product.image.name
        old_variant = variant_name(old_name, 320)
        self.assertTrue(product.image.storage.exists(old_name))
        self.assertTrue(product.image.storage.exists(old_variant))

        product.image = uploaded_image("new.jpg", size=(640, 320))
        product.save(update_fields=["image"])
        product.refresh_from_db()
        new_name = product.image.name
        new_variant = variant_name(new_name, 320)

        self.assertNotEqual(new_name, old_name)
        self.assertFalse(product.image.storage.exists(old_name))
        self.assertFalse(product.image.storage.exists(old_variant))
        self.assertTrue(product.image.storage.exists(new_name))
        self.assertTrue(product.image.storage.exists(new_variant))

        storage = product.image.storage
        product.delete()
        self.assertFalse(storage.exists(new_name))
        self.assertFalse(storage.exists(new_variant))
