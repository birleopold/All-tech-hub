import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings
from PIL import Image, ImageDraw

from catalog.product_studio import prepare_product_image, render_product_upload
from catalog.studio_watermarks import _archive_original_for_processed_digest


def _source_bytes(size=(800, 600), colour=(245, 245, 245)):
    image = Image.new("RGB", size, colour)
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _fake_product_segmenter(image):
    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(output)
    width, height = image.size
    draw.rounded_rectangle(
        (
            round(width * 0.22),
            round(height * 0.18),
            round(width * 0.78),
            round(height * 0.86),
        ),
        radius=max(4, round(min(width, height) * 0.03)),
        fill=(45, 95, 155, 255),
    )
    return output


class ProductStudioTests(SimpleTestCase):
    @override_settings(
        PRODUCT_IMAGE_STUDIO_ENABLED=True,
        PRODUCT_IMAGE_STUDIO_STYLE="clean_studio",
        PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH=1000,
        PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT=1000,
        PRODUCT_IMAGE_STUDIO_PADDING=0.12,
        PRODUCT_IMAGE_STUDIO_BASE_COLOR="#f6f6f8",
    )
    def test_clean_studio_centres_product_on_uniform_catalogue_canvas(self):
        source = Image.new("RGBA", (800, 600), (245, 245, 245, 255))

        result = prepare_product_image(source, segmenter=_fake_product_segmenter)

        self.assertTrue(result.applied)
        self.assertEqual(result.image.size, (1000, 1000))
        self.assertEqual(result.image.getpixel((0, 0)), (236, 236, 238, 255))
        centre = result.image.getpixel((500, 500))
        self.assertEqual(centre[:3], (45, 95, 155))

    @override_settings(
        PRODUCT_IMAGE_STUDIO_ENABLED=True,
        PRODUCT_IMAGE_STUDIO_STYLE="transparent",
        PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH=1000,
        PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT=1000,
        PRODUCT_IMAGE_STUDIO_PADDING=0.12,
    )
    def test_transparent_style_keeps_real_alpha_without_dark_edge_compositing(self):
        source = Image.new("RGBA", (800, 600), (245, 245, 245, 255))

        result = prepare_product_image(source, segmenter=_fake_product_segmenter)

        self.assertTrue(result.applied)
        self.assertEqual(result.output_format, "PNG")
        self.assertEqual(result.image.getpixel((0, 0)), (0, 0, 0, 0))
        alpha_box = result.image.getchannel("A").getbbox()
        self.assertIsNotNone(alpha_box)
        left, top, right, bottom = alpha_box
        self.assertGreater(left, 40)
        self.assertGreater(top, 40)
        self.assertLess(right, 960)
        self.assertLess(bottom, 960)

    @override_settings(
        PRODUCT_IMAGE_STUDIO_ENABLED=True,
        PRODUCT_IMAGE_STUDIO_STYLE="clean_studio",
        PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH=900,
        PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT=900,
    )
    def test_render_product_upload_returns_marketplace_jpeg(self):
        rendered, name, applied = render_product_upload(
            _source_bytes(),
            "camera-phone.jpg",
            segmenter=_fake_product_segmenter,
        )

        self.assertTrue(applied)
        self.assertEqual(name, "camera-phone-studio.jpg")
        with Image.open(BytesIO(rendered)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (900, 900))

    @override_settings(
        PRODUCT_IMAGE_STUDIO_ENABLED=True,
        PRODUCT_IMAGE_STUDIO_STYLE="clean_studio",
    )
    def test_segmentation_failure_preserves_original_upload(self):
        raw = _source_bytes()
        failing_segmenter = Mock(side_effect=RuntimeError("model unavailable"))

        rendered, name, applied = render_product_upload(
            raw,
            "laptop.jpg",
            segmenter=failing_segmenter,
        )

        self.assertFalse(applied)
        self.assertEqual(name, "laptop.jpg")
        self.assertEqual(rendered, raw)

    @override_settings(PRODUCT_IMAGE_STUDIO_ENABLED=False)
    def test_disabled_studio_does_not_call_segmenter(self):
        source = Image.new("RGBA", (300, 200), (10, 20, 30, 255))
        segmenter = Mock()

        result = prepare_product_image(source, segmenter=segmenter)

        self.assertFalse(result.applied)
        self.assertEqual(result.image.size, source.size)
        segmenter.assert_not_called()

    def test_archive_alias_keeps_true_original_for_processed_digest_rebuilds(self):
        original = _source_bytes(size=(640, 480), colour=(220, 225, 230))
        processed = _source_bytes(size=(1000, 1000), colour=(246, 246, 248))
        digest = hashlib.sha256(processed).hexdigest()[:16]

        with TemporaryDirectory() as private_root:
            with override_settings(
                PRIVATE_MEDIA_ROOT=private_root,
                PRODUCT_IMAGE_ARCHIVE_ORIGINALS=True,
            ):
                alias = _archive_original_for_processed_digest(
                    original,
                    "raw-phone.jpg",
                    processed,
                    "raw-phone-studio.jpg",
                )

            self.assertIsNotNone(alias)
            self.assertTrue(alias.exists())
            self.assertEqual(alias.read_bytes(), original)
            self.assertIn(digest, alias.stem)
            originals = list(Path(private_root).rglob("raw-phone-*.jpg"))
            self.assertGreaterEqual(len(originals), 2)
