"""Bridge the optional product studio into the existing watermark pipeline."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

from catalog import watermarks
from catalog.product_studio import render_product_upload, studio_enabled

logger = logging.getLogger(__name__)


def _archive_original_for_processed_digest(
    original_raw: bytes,
    original_name: str,
    processed_raw: bytes,
    processed_name: str,
) -> Path | None:
    """Keep the true original restorable through the existing digest lookup."""

    if not original_raw or not processed_raw or not watermarks._archive_enabled():
        return None

    true_original = watermarks._archive_original(original_raw, original_name)
    digest = hashlib.sha256(processed_raw).hexdigest()[:16]
    stem = slugify(Path(processed_name or "product").stem)[:80] or "product"
    suffix = Path(processed_name or "").suffix.lower() or ".img"
    dated = datetime.now(timezone.utc).strftime("%Y/%m")
    folder = watermarks._private_archive_root() / dated
    folder.mkdir(parents=True, exist_ok=True)
    alias = folder / f"{stem}-{digest}{suffix}"

    if not alias.exists():
        try:
            if true_original and true_original.exists():
                os.link(true_original, alias)
            else:
                alias.write_bytes(original_raw)
        except OSError:
            alias.write_bytes(original_raw)
    return alias


def watermark_pending_model_image(instance, field_name: str = "image") -> bool:
    """Run studio preparation before the established enhancement/watermark step."""

    field_file = getattr(instance, field_name, None)
    if (
        not studio_enabled()
        or not field_file
        or getattr(field_file, "_committed", True)
        or Path(field_file.name or "").name.startswith(watermarks.WATERMARK_PREFIX)
    ):
        return watermarks.watermark_pending_model_image(instance, field_name)

    try:
        original_raw = watermarks._read_field_file(field_file)
        processed_raw, processed_name, applied = render_product_upload(
            original_raw,
            field_file.name,
        )
        if not applied:
            return watermarks.watermark_pending_model_image(instance, field_name)

        _archive_original_for_processed_digest(
            original_raw,
            field_file.name,
            processed_raw,
            processed_name,
        )
        setattr(
            instance,
            field_name,
            ContentFile(processed_raw, name=processed_name),
        )
        watermarked = watermarks.watermark_pending_model_image(instance, field_name)
        return bool(applied or watermarked)
    except Exception:
        logger.exception(
            "Could not bridge product studio for %s.%s; using the normal pipeline.",
            instance.__class__.__name__,
            field_name,
        )
        return watermarks.watermark_pending_model_image(instance, field_name)
