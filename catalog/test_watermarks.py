from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw

from catalog.models import Category, Product, ProductImage
from catalog.watermarks import _enhance_image


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
            PRODUCT_IMAGE_ENHANCEMENT_ENABLED=True,
            PRODUCT_IMAGE_ARCHIVE_ORIGINALS=True,
            PRODUCT_IMAGE_WATERMARK_TEXT="LEOSOFT UG LTD • leosoftug.com",
            PRODUCT_IMAGE_WATERMARK_OPACITY=65,
            PRODUCT_IMAGE_WATERMARK_MAX_WIDTH=1200,
            PRODUCT_IMAGE_MAX_BRIGHTNESS_GAIN=1.06,
            PRODUCT_IMAGE_MAX_CONTRAST_GAIN=1.04,
            PRODUCT_IMAGE_SHARPEN_PERCENT=35,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.addCleanup(self.private_dir.cleanup)
        self.category = Category.objects.create(name="Computers", slug="computers")

    def test_primary_product_upload_is_processed_once(self):
        upload = _uploaded_image()
        original_bytes = upload.read()
        upload.seek(0)
        product = Product.objects.create(
            category=self.category,
            name="Watermark Test Laptop",
            price="2500000.00",
            stock_quantity=2,
            image=upload,
        )

        filename = Path(product.image.name).name
        self.assertTrue(filename.startswith("wm_"))
        self.assertTrue(Path(product.image.path).exists())
        with Image.open(product.image.path) as image:
            self.assertEqual(image.size, (900, 650))
            self.assertEqual(image.format, "JPEG")

        archived = list(Path(self.private_dir.name).rglob("*.jpg"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), original_bytes)

        first_name = product.image.name
        product.price = "2400000.00"
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.image.name, first_name)

    def test_tiny_gallery_image_does_not_crash_watermark_layout(self):
        product = Product.objects.create(
            category=self.category,
            name="Tiny preview product",
            price="180000.00",
            stock_quantity=1,
        )
        gallery = ProductImage.objects.create(
            product=product,
            image=_uploaded_image("tiny-preview.jpg", size=(20, 20)),
            alt_text="Tiny source image",
        )
        self.assertTrue(Path(gallery.image.name).name.startswith("wm_"))
        with Image.open(gallery.image.path) as image:
            self.assertEqual(image.size, (20, 20))

    def test_gallery_upload_is_processed(self):
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

    def test_resize_preserves_aspect_ratio_and_never_enlarges(self):
        product = Product.objects.create(
            category=self.category,
            name="Wide Laptop Image",
            price="2100000.00",
            stock_quantity=1,
            image=_uploaded_image("wide.jpg", size=(2400, 1200)),
        )
        with Image.open(product.image.path) as image:
            self.assertEqual(image.size, (1200, 600))

        small = Product.objects.create(
            category=self.category,
            name="Small Laptop Image",
            price="1100000.00",
            stock_quantity=1,
            image=_uploaded_image("small.jpg", size=(500, 300)),
        )
        with Image.open(small.image.path) as image:
            self.assertEqual(image.size, (500, 300))

    def test_enhancement_preserves_dimensions_and_alpha(self):
        image = Image.new("RGBA", (640, 360), (45, 70, 95, 120))
        enhanced = _enhance_image(image)

        self.assertEqual(enhanced.size, image.size)
        self.assertEqual(enhanced.getchannel("A").getextrema(), (120, 120))

    def test_balanced_image_colours_are_not_changed(self):
        image = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 49, 99), fill=(20, 20, 20, 255))
        draw.rectangle((50, 0, 99, 99), fill=(240, 240, 240, 255))

        with override_settings(PRODUCT_IMAGE_SHARPEN_PERCENT=0):
            enhanced = _enhance_image(image)

        self.assertEqual(list(enhanced.getdata()), list(image.getdata()))

    def test_dark_image_brightness_lift_is_gentle_and_capped(self):
        image = Image.new("RGBA", (100, 100), (40, 50, 60, 255))
        with override_settings(
            PRODUCT_IMAGE_MAX_BRIGHTNESS_GAIN=1.06,
            PRODUCT_IMAGE_MAX_CONTRAST_GAIN=1.0,
            PRODUCT_IMAGE_SHARPEN_PERCENT=0,
        ):
            enhanced = _enhance_image(image)

        red, green, blue, alpha = enhanced.getpixel((50, 50))
        self.assertGreaterEqual(red, 40)
        self.assertGreaterEqual(green, 50)
        self.assertGreaterEqual(blue, 60)
        self.assertLessEqual(red, 45)
        self.assertLessEqual(green, 56)
        self.assertLessEqual(blue, 68)
        self.assertEqual(alpha, 255)

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

    def test_watermarked_image_can_be_rebuilt_from_private_original(self):
        product = Product.objects.create(
            category=self.category,
            name="Reprocess Laptop",
            price="1900000.00",
            stock_quantity=1,
            image=_uploaded_image("reprocess.jpg"),
        )
        old_name = product.image.name
        old_path = Path(product.image.path)
        self.assertTrue(old_path.exists())
        self.assertEqual(len(list(Path(self.private_dir.name).rglob("*.jpg"))), 1)

        call_command("reprocess_product_images")
        product.refresh_from_db()

        self.assertTrue(Path(product.image.name).name.startswith("wm_"))
        self.assertTrue(Path(product.image.path).exists())
        self.assertNotEqual(product.image.name, old_name)
        self.assertFalse(old_path.exists())
        self.assertEqual(len(list(Path(self.private_dir.name).rglob("*.jpg"))), 1)
