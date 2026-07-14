from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from catalog.models import Category, Product, ProductImage


def _uploaded_image(name="laptop.jpg", size=(900, 650), colour=(35, 90, 145)):
    output = BytesIO()
    Image.new("RGB", size, colour).save(output, format="JPEG", quality=95)
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


class ProductImageWatermarkTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.private_dir = TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_dir.name,
            PRIVATE_MEDIA_ROOT=self.private_dir.name,
            PRODUCT_IMAGE_WATERMARK_ENABLED=True,
            PRODUCT_IMAGE_ARCHIVE_ORIGINALS=True,
            PRODUCT_IMAGE_WATERMARK_TEXT="LEOSOFT UG LTD • leosoftug.com",
            PRODUCT_IMAGE_WATERMARK_OPACITY=65,
            PRODUCT_IMAGE_WATERMARK_MAX_WIDTH=1200,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.addCleanup(self.private_dir.cleanup)
        self.category = Category.objects.create(name="Computers", slug="computers")

    def test_primary_product_upload_is_watermarked_once(self):
        product = Product.objects.create(
            category=self.category,
            name="Watermark Test Laptop",
            price="2500000.00",
            stock_quantity=2,
            image=_uploaded_image(),
        )

        filename = Path(product.image.name).name
        self.assertTrue(filename.startswith("wm_"))
        self.assertTrue(Path(product.image.path).exists())
        with Image.open(product.image.path) as image:
            self.assertEqual(image.size, (900, 650))
            self.assertEqual(image.format, "JPEG")

        archived = list(Path(self.private_dir.name).rglob("*.jpg"))
        self.assertEqual(len(archived), 1)

        first_name = product.image.name
        product.price = "2400000.00"
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.image.name, first_name)

    def test_gallery_upload_is_watermarked(self):
        product = Product.objects.create(
            category=self.category,
            name="Gallery Laptop",
            price="1800000.00",
            stock_quantity=1,
        )
        gallery = ProductImage.objects.create(
            product=product,
            image=_uploaded_image("gallery.jpg", size=(700, 700)),
            alt_text="Laptop side view",
        )

        self.assertTrue(Path(gallery.image.name).name.startswith("wm_"))
        self.assertTrue(Path(gallery.image.path).exists())

    def test_existing_image_backfill_command(self):
        with override_settings(PRODUCT_IMAGE_WATERMARK_ENABLED=False):
            product = Product.objects.create(
                category=self.category,
                name="Existing Image Laptop",
                price="1600000.00",
                stock_quantity=1,
                image=_uploaded_image("existing.jpg"),
            )
        self.assertFalse(Path(product.image.name).name.startswith("wm_"))

        call_command("watermark_product_images")
        product.refresh_from_db()
        self.assertTrue(Path(product.image.name).name.startswith("wm_"))
        self.assertTrue(Path(product.image.path).exists())
