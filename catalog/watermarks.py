"""Enhance and watermark public product images while retaining private originals."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import (
    Image,
    ImageCms,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageStat,
)

logger = logging.getLogger(__name__)

WATERMARK_PREFIX = "wm_"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_float(
    setting_name: str,
    env_name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = getattr(settings, setting_name, None)
    if raw is None:
        raw = os.getenv(env_name, str(default))
    try:
        return max(minimum, min(maximum, float(raw)))
    except (TypeError, ValueError):
        return default


def _bounded_int(
    setting_name: str,
    env_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = getattr(settings, setting_name, None)
    if raw is None:
        raw = os.getenv(env_name, str(default))
    try:
        return max(minimum, min(maximum, int(raw)))
    except (TypeError, ValueError):
        return default


def _enabled() -> bool:
    configured = getattr(settings, "PRODUCT_IMAGE_WATERMARK_ENABLED", None)
    if configured is not None:
        return bool(configured)
    return _env_bool("ALLTECH_PRODUCT_IMAGE_WATERMARK_ENABLED", True)


def _enhancement_enabled() -> bool:
    configured = getattr(settings, "PRODUCT_IMAGE_ENHANCEMENT_ENABLED", None)
    if configured is not None:
        return bool(configured)
    return _env_bool("ALLTECH_PRODUCT_IMAGE_ENHANCEMENT_ENABLED", True)


def _archive_enabled() -> bool:
    configured = getattr(settings, "PRODUCT_IMAGE_ARCHIVE_ORIGINALS", None)
    if configured is not None:
        return bool(configured)
    return _env_bool("ALLTECH_PRODUCT_IMAGE_ARCHIVE_ORIGINALS", True)


def _watermark_text() -> str:
    return str(
        getattr(settings, "PRODUCT_IMAGE_WATERMARK_TEXT", None)
        or os.getenv(
            "ALLTECH_PRODUCT_IMAGE_WATERMARK_TEXT",
            "LEOSOFT UG LTD • leosoftug.com",
        )
    ).strip()


def _opacity() -> int:
    return _bounded_int(
        "PRODUCT_IMAGE_WATERMARK_OPACITY",
        "ALLTECH_PRODUCT_IMAGE_WATERMARK_OPACITY",
        58,
        20,
        150,
    )


def _max_width() -> int:
    return _bounded_int(
        "PRODUCT_IMAGE_WATERMARK_MAX_WIDTH",
        "ALLTECH_PRODUCT_IMAGE_WATERMARK_MAX_WIDTH",
        1800,
        600,
        4000,
    )


def _max_brightness_gain() -> float:
    return _bounded_float(
        "PRODUCT_IMAGE_MAX_BRIGHTNESS_GAIN",
        "ALLTECH_PRODUCT_IMAGE_MAX_BRIGHTNESS_GAIN",
        1.06,
        1.0,
        1.12,
    )


def _max_contrast_gain() -> float:
    return _bounded_float(
        "PRODUCT_IMAGE_MAX_CONTRAST_GAIN",
        "ALLTECH_PRODUCT_IMAGE_MAX_CONTRAST_GAIN",
        1.04,
        1.0,
        1.10,
    )


def _sharpen_percent() -> int:
    return _bounded_int(
        "PRODUCT_IMAGE_SHARPEN_PERCENT",
        "ALLTECH_PRODUCT_IMAGE_SHARPEN_PERCENT",
        35,
        0,
        80,
    )


def _private_archive_root() -> Path:
    configured = getattr(settings, "PRIVATE_MEDIA_ROOT", None)
    if configured:
        return Path(configured) / "product_originals"
    return Path(settings.BASE_DIR) / "private_media" / "product_originals"


def _font(size: int, *, bold: bool = False):
    candidates = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _safe_extension(original_name: str, image_format: str | None) -> tuple[str, str]:
    suffix = Path(original_name or "").suffix.lower()
    if suffix == ".png" or image_format == "PNG":
        return ".png", "PNG"
    if suffix == ".webp" or image_format == "WEBP":
        return ".webp", "WEBP"
    return ".jpg", "JPEG"


def _archive_original(raw: bytes, original_name: str) -> Path | None:
    if not _archive_enabled() or not raw:
        return None
    digest = hashlib.sha256(raw).hexdigest()[:16]
    stem = slugify(Path(original_name or "product").stem)[:80] or "product"
    suffix = Path(original_name or "").suffix.lower() or ".img"
    dated = datetime.now(timezone.utc).strftime("%Y/%m")
    folder = _private_archive_root() / dated
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{stem}-{digest}{suffix}"
    if not destination.exists():
        destination.write_bytes(raw)
    return destination


def _read_field_file(field_file) -> bytes:
    source = getattr(field_file, "file", field_file)
    if hasattr(source, "seek"):
        source.seek(0)
    raw = source.read()
    if hasattr(source, "seek"):
        source.seek(0)
    return raw


def _normalise_to_srgb_rgba(opened: Image.Image) -> Image.Image:
    """Correct EXIF orientation and normalise colour without changing geometry."""

    oriented = ImageOps.exif_transpose(opened)
    rgba = oriented.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    icc_profile = opened.info.get("icc_profile")

    if icc_profile:
        try:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            target_profile = ImageCms.createProfile("sRGB")
            rgb = ImageCms.profileToProfile(
                rgb,
                source_profile,
                target_profile,
                outputMode="RGB",
            )
        except Exception:
            logger.debug(
                "Could not convert embedded profile to sRGB; using RGB conversion.",
                exc_info=True,
            )

    normalised = rgb.convert("RGBA")
    normalised.putalpha(alpha)
    return normalised


def _enhance_image(image: Image.Image) -> Image.Image:
    """Apply capped corrections while preserving size, ratio, alpha and colour."""

    rgba = image.convert("RGBA")
    if not _enhancement_enabled():
        return rgba

    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    luminance = ImageOps.grayscale(rgb)
    statistics = ImageStat.Stat(luminance)
    mean_luminance = float(statistics.mean[0])
    luminance_spread = float(statistics.stddev[0])

    # Lift only genuinely dark images and never exceed the configured cap.
    if mean_luminance < 112:
        deficit = min(1.0, max(0.0, (112.0 - mean_luminance) / 112.0))
        factor = 1.0 + ((_max_brightness_gain() - 1.0) * deficit)
        if factor > 1.0:
            rgb = ImageEnhance.Brightness(rgb).enhance(factor)

    # Add only slight contrast to flat images. Balanced images remain unchanged.
    if luminance_spread < 46:
        deficit = min(1.0, max(0.0, (46.0 - luminance_spread) / 46.0))
        factor = 1.0 + ((_max_contrast_gain() - 1.0) * deficit)
        if factor > 1.0:
            rgb = ImageEnhance.Contrast(rgb).enhance(factor)

    sharpen_percent = _sharpen_percent()
    if sharpen_percent:
        rgb = rgb.filter(
            ImageFilter.UnsharpMask(
                radius=0.8,
                percent=sharpen_percent,
                threshold=5,
            )
        )

    enhanced = rgb.convert("RGBA")
    enhanced.putalpha(alpha)
    return enhanced


def _fit_brand_font(text: str, max_width: int, preferred_size: int):
    size = max(12, preferred_size)
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    while size > 12:
        font = _font(size, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font, bbox
        size -= 2
    font = _font(12, bold=True)
    return font, draw.textbbox((0, 0), text, font=font)


def _render_watermark(raw: bytes, original_name: str) -> tuple[bytes, str]:
    with Image.open(BytesIO(raw)) as opened:
        image_format = opened.format
        image = _normalise_to_srgb_rgba(opened)

    max_width = _max_width()
    if image.width > max_width:
        height = max(1, round(image.height * max_width / image.width))
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)

    image = _enhance_image(image)
    width, height = image.size
    text = _watermark_text() or "LEOSOFT UG LTD • leosoftug.com"
    opacity = _opacity()
    font_size = max(20, min(72, round(min(width, height) * 0.045)))
    repeat_font = _font(font_size, bold=True)

    sample = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    sample_draw = ImageDraw.Draw(sample)
    bbox = sample_draw.textbbox((0, 0), text, font=repeat_font, stroke_width=1)
    text_width = max(1, bbox[2] - bbox[0])
    text_height = max(1, bbox[3] - bbox[1])
    tile = Image.new(
        "RGBA",
        (text_width + font_size * 2, text_height + font_size),
        (0, 0, 0, 0),
    )
    tile_draw = ImageDraw.Draw(tile)
    tile_draw.text(
        (font_size, font_size // 3),
        text,
        font=repeat_font,
        fill=(255, 255, 255, opacity),
        stroke_width=max(1, font_size // 18),
        stroke_fill=(0, 0, 0, max(25, opacity // 2)),
    )
    tile = tile.rotate(28, expand=True, resample=Image.Resampling.BICUBIC)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    x_step = max(tile.width + font_size, round(width * 0.48))
    y_step = max(tile.height + font_size, round(height * 0.28))
    for y in range(-tile.height, height + tile.height, y_step):
        row_offset = -(x_step // 2) if (y // y_step) % 2 else 0
        for x in range(-tile.width + row_offset, width + tile.width, x_step):
            overlay.alpha_composite(tile, (x, y))

    brand = "LEOSOFT UG LTD  •  leosoftug.com"
    horizontal_margin = max(10, width // 50)
    padding_x = max(12, font_size // 2)
    padding_y = max(9, font_size // 3)
    available_text_width = max(80, width - (horizontal_margin * 2) - (padding_x * 2))
    brand_font, brand_bbox = _fit_brand_font(
        brand,
        available_text_width,
        max(20, min(52, round(min(width, height) * 0.042))),
    )
    brand_width = brand_bbox[2] - brand_bbox[0]
    brand_height = brand_bbox[3] - brand_bbox[1]
    right = width - horizontal_margin
    bottom = height - max(10, height // 50)
    left = max(horizontal_margin, right - brand_width - padding_x * 2)
    top = max(10, bottom - brand_height - padding_y * 2)
    # Tiny thumbnails cannot fit the branded corner plaque. The repeated
    # watermark above remains, and the original dimensions are preserved.
    # Never draw an inverted rectangle (Pillow raises ValueError for it).
    if width >= 160 and height >= 80:
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=max(8, padding_y),
            fill=(8, 25, 44, 205),
            outline=(255, 255, 255, 180),
            width=max(1, font_size // 22),
        )
        overlay_draw.text(
            (left + padding_x, top + padding_y),
            brand,
            font=brand_font,
            fill=(255, 255, 255, 245),
        )

    watermarked = Image.alpha_composite(image, overlay)
    extension, output_format = _safe_extension(original_name, image_format)
    output = BytesIO()
    if output_format == "PNG":
        watermarked.save(output, format="PNG", optimize=True)
    elif output_format == "WEBP":
        watermarked.convert("RGB").save(
            output,
            format="WEBP",
            quality=90,
            method=6,
        )
    else:
        background = Image.new("RGB", watermarked.size, (255, 255, 255))
        background.paste(watermarked, mask=watermarked.getchannel("A"))
        background.save(
            output,
            format="JPEG",
            quality=92,
            optimize=True,
            progressive=True,
            subsampling=0,
        )
    return output.getvalue(), extension


def _watermarked_name(original_name: str, raw: bytes, extension: str) -> str:
    stem = slugify(Path(original_name or "product").stem)[:90] or "product"
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"{WATERMARK_PREFIX}{stem}-{digest}{extension}"


def watermark_pending_model_image(instance, field_name: str = "image") -> bool:
    """Enhance and watermark an uncommitted upload before its model is saved."""

    if not _enabled():
        return False
    field_file = getattr(instance, field_name, None)
    if not field_file or getattr(field_file, "_committed", True):
        return False
    if Path(field_file.name or "").name.startswith(WATERMARK_PREFIX):
        return False

    try:
        raw = _read_field_file(field_file)
        if not raw:
            return False
        _archive_original(raw, field_file.name)
        rendered, extension = _render_watermark(raw, field_file.name)
        name = _watermarked_name(field_file.name, raw, extension)
        field_file.save(name, ContentFile(rendered), save=False)
        return True
    except Exception:
        logger.exception(
            "Could not process uploaded image for %s.%s; preserving the upload.",
            instance.__class__.__name__,
            field_name,
        )
        return False


def watermark_stored_model_image(instance, field_name: str = "image", *, force=False) -> bool:
    """Replace an existing public image with an enhanced, watermarked copy."""

    if not _enabled():
        return False
    field_file = getattr(instance, field_name, None)
    if not field_file or not field_file.name:
        return False
    if Path(field_file.name).name.startswith(WATERMARK_PREFIX) and not force:
        return False

    old_name = field_file.name
    try:
        field_file.open("rb")
        raw = field_file.read()
        field_file.close()
        if not raw:
            return False
        _archive_original(raw, old_name)
        rendered, extension = _render_watermark(raw, old_name)
        content_name = _watermarked_name(old_name, raw, extension)
        model_field = instance._meta.get_field(field_name)
        generated_name = model_field.generate_filename(instance, content_name)
        new_name = field_file.storage.save(generated_name, ContentFile(rendered))
        instance.__class__.objects.filter(pk=instance.pk).update(**{field_name: new_name})
        setattr(instance, field_name, new_name)
        if old_name != new_name:
            field_file.storage.delete(old_name)
        return True
    except Exception:
        logger.exception(
            "Could not process stored image for %s pk=%s.",
            instance.__class__.__name__,
            instance.pk,
        )
        return False
