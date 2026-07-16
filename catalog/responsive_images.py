"""Responsive public image derivatives for catalogue and product pages."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

DEFAULT_WIDTHS = (320, 640, 960, 1280)


def responsive_images_enabled() -> bool:
    return bool(getattr(settings, "PRODUCT_IMAGE_RESPONSIVE_ENABLED", True))


def responsive_widths() -> tuple[int, ...]:
    configured = getattr(settings, "PRODUCT_IMAGE_RESPONSIVE_WIDTHS", DEFAULT_WIDTHS)
    values = []
    for raw in configured:
        try:
            width = int(raw)
        except (TypeError, ValueError):
            continue
        if 160 <= width <= 2400:
            values.append(width)
    return tuple(sorted(set(values))) or DEFAULT_WIDTHS


def responsive_quality() -> int:
    try:
        value = int(getattr(settings, "PRODUCT_IMAGE_RESPONSIVE_QUALITY", 84))
    except (TypeError, ValueError):
        value = 84
    return max(60, min(95, value))


def variant_name(source_name: str, width: int) -> str:
    source = PurePosixPath(source_name)
    directory = source.parent / "responsive" / source.stem
    return str(directory / f"w{int(width)}.webp")


def existing_responsive_sources(field_file) -> list[tuple[int, str]]:
    if not responsive_images_enabled() or not field_file or not field_file.name:
        return []
    sources = []
    storage = field_file.storage
    for width in responsive_widths():
        name = variant_name(field_file.name, width)
        try:
            if storage.exists(name):
                sources.append((width, storage.url(name)))
        except Exception:
            logger.debug("Could not inspect responsive derivative %s", name, exc_info=True)
    return sources


def generate_responsive_variants(field_file, *, force: bool = False) -> list[str]:
    """Generate proportional WebP derivatives without enlarging the source image."""

    if not responsive_images_enabled() or not field_file or not field_file.name:
        return []

    storage = field_file.storage
    generated = []
    try:
        field_file.open("rb")
        raw = field_file.read()
        field_file.close()
        if not raw:
            return []

        with Image.open(BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")
        source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            return []

        for width in responsive_widths():
            if width > source_width:
                continue
            name = variant_name(field_file.name, width)
            if not force and storage.exists(name):
                generated.append(name)
                continue
            if force and storage.exists(name):
                storage.delete(name)

            height = max(1, round(source_height * width / source_width))
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            output = BytesIO()
            resized.save(
                output,
                format="WEBP",
                quality=responsive_quality(),
                method=6,
            )
            saved_name = storage.save(name, ContentFile(output.getvalue()))
            generated.append(saved_name)
    except Exception:
        logger.exception("Could not generate responsive image variants for %s", field_file.name)
    return generated


def purge_responsive_variants(field_file) -> int:
    if not field_file or not field_file.name:
        return 0
    deleted = 0
    storage = field_file.storage
    for width in responsive_widths():
        name = variant_name(field_file.name, width)
        try:
            if storage.exists(name):
                storage.delete(name)
                deleted += 1
        except Exception:
            logger.debug("Could not delete responsive derivative %s", name, exc_info=True)
    return deleted


def source_dimensions(field_file) -> tuple[int | None, int | None]:
    if not field_file:
        return None, None
    try:
        return int(field_file.width), int(field_file.height)
    except Exception:
        return None, None
