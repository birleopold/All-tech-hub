"""Optional AI product-photo preparation for catalogue uploads.

The studio stage runs before the existing enhancement, watermark and responsive
image pipeline. It deliberately fails open: if the optional AI dependency or
model is unavailable, the original upload continues through the normal pipeline.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from django.conf import settings
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

Segmenter = Callable[[Image.Image], Image.Image]
_ALLOWED_STYLES = {"clean_studio", "cinematic_blur", "transparent", "preserve"}
_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, object] = {}


class ProductStudioError(RuntimeError):
    """Base error for product studio failures."""


class ProductStudioDependencyError(ProductStudioError):
    """Raised when the optional rembg runtime is not installed."""


class ProductStudioSubjectError(ProductStudioError):
    """Raised when segmentation does not find a usable foreground subject."""


@dataclass(frozen=True)
class StudioResult:
    image: Image.Image
    output_format: str | None = None
    applied: bool = False


def _configured(setting_name: str, env_name: str, default):
    value = getattr(settings, setting_name, None)
    if value is not None:
        return value
    return os.getenv(env_name, default)


def _configured_bool(setting_name: str, env_name: str, default: bool) -> bool:
    value = _configured(setting_name, env_name, "1" if default else "0")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def studio_enabled() -> bool:
    return _configured_bool(
        "PRODUCT_IMAGE_STUDIO_ENABLED",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_ENABLED",
        False,
    )


def studio_style() -> str:
    value = str(
        _configured(
            "PRODUCT_IMAGE_STUDIO_STYLE",
            "ALLTECH_PRODUCT_IMAGE_STUDIO_STYLE",
            "clean_studio",
        )
    ).strip().lower()
    return value if value in _ALLOWED_STYLES else "clean_studio"


def studio_model() -> str:
    return (
        str(
            _configured(
                "PRODUCT_IMAGE_STUDIO_MODEL",
                "ALLTECH_PRODUCT_IMAGE_STUDIO_MODEL",
                "isnet-general-use",
            )
        ).strip()
        or "isnet-general-use"
    )


def _bounded_int(
    setting_name: str,
    env_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(_configured(setting_name, env_name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(
    setting_name: str,
    env_name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(_configured(setting_name, env_name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _canvas_size() -> tuple[int, int]:
    return (
        _bounded_int(
            "PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH",
            "ALLTECH_PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH",
            1600,
            600,
            3000,
        ),
        _bounded_int(
            "PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT",
            "ALLTECH_PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT",
            1600,
            600,
            3000,
        ),
    )


def _base_colour() -> tuple[int, int, int]:
    raw = _configured(
        "PRODUCT_IMAGE_STUDIO_BASE_COLOR",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_BASE_COLOR",
        "#f6f6f8",
    )
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        try:
            return tuple(max(0, min(255, int(channel))) for channel in raw)
        except (TypeError, ValueError):
            return (246, 246, 248)

    value = str(raw).strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            pass
    return (246, 246, 248)


def _session_for(model_name: str):
    with _SESSION_LOCK:
        cached = _SESSIONS.get(model_name)
        if cached is not None:
            return cached
        try:
            from rembg import new_session
        except ImportError as exc:
            raise ProductStudioDependencyError(
                'Install the optional CPU runtime with: pip install "rembg[cpu]"'
            ) from exc
        session = new_session(model_name)
        _SESSIONS[model_name] = session
        return session


def warm_studio_model() -> str:
    """Load/download the configured model and return its name."""

    model_name = studio_model()
    _session_for(model_name)
    return model_name


def _default_segmenter(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove
    except ImportError as exc:
        raise ProductStudioDependencyError(
            'Install the optional CPU runtime with: pip install "rembg[cpu]"'
        ) from exc

    result = remove(
        image,
        session=_session_for(studio_model()),
        post_process_mask=True,
    )
    if not isinstance(result, Image.Image):
        raise ProductStudioError("rembg returned an unsupported image result.")
    return result.convert("RGBA")


def _limit_dimensions(image: Image.Image) -> Image.Image:
    max_dimension = _bounded_int(
        "PRODUCT_IMAGE_STUDIO_MAX_INPUT_DIMENSION",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_MAX_INPUT_DIMENSION",
        2400,
        800,
        5000,
    )
    bounded = image.copy()
    if max(bounded.size) > max_dimension:
        bounded.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return bounded


def _refine_alpha(alpha: Image.Image) -> Image.Image:
    """Close tiny mask holes and soften only the final sub-pixel edge."""

    refined = alpha.convert("L")
    if min(refined.size) >= 3:
        refined = refined.filter(ImageFilter.MaxFilter(3))
        refined = refined.filter(ImageFilter.MinFilter(3))
    return refined.filter(ImageFilter.GaussianBlur(radius=0.65))


def _subject_box(alpha: Image.Image) -> tuple[int, int, int, int]:
    threshold = _bounded_int(
        "PRODUCT_IMAGE_STUDIO_ALPHA_THRESHOLD",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_ALPHA_THRESHOLD",
        8,
        1,
        80,
    )
    binary = alpha.point(lambda value: 255 if value > threshold else 0)
    bbox = binary.getbbox()
    if not bbox:
        raise ProductStudioSubjectError("No clear product was detected.")
    return bbox


def _expanded_box(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width = max(1, right - left)
    height = max(1, bottom - top)
    context = _bounded_float(
        "PRODUCT_IMAGE_STUDIO_CROP_CONTEXT",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_CROP_CONTEXT",
        0.025,
        0.0,
        0.15,
    )
    margin = round(max(width, height) * context)
    image_width, image_height = image_size
    return (
        max(0, left - margin),
        max(0, top - margin),
        min(image_width, right + margin),
        min(image_height, bottom + margin),
    )


def _fit_product(product: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    canvas_width, canvas_height = _canvas_size()
    padding = _bounded_float(
        "PRODUCT_IMAGE_STUDIO_PADDING",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_PADDING",
        0.12,
        0.04,
        0.30,
    )
    available_width = max(1, round(canvas_width * (1.0 - 2.0 * padding)))
    available_height = max(1, round(canvas_height * (1.0 - 2.0 * padding)))
    scale = min(
        available_width / max(1, product.width),
        available_height / max(1, product.height),
    )
    target_size = (
        max(1, round(product.width * scale)),
        max(1, round(product.height * scale)),
    )
    fitted = product.resize(target_size, Image.Resampling.LANCZOS)
    offset = (
        (canvas_width - fitted.width) // 2,
        (canvas_height - fitted.height) // 2,
    )
    return fitted, offset


def _gradient_background() -> Image.Image:
    width, height = _canvas_size()
    base = _base_colour()
    top = tuple(max(0, channel - 10) for channel in base)
    bottom = tuple(min(255, channel + 2) for channel in base)
    strip = Image.new("RGB", (1, height))
    pixels = []
    denominator = max(1, height - 1)
    for row in range(height):
        weight = row / denominator
        pixels.append(
            tuple(
                round(top[index] + (bottom[index] - top[index]) * weight)
                for index in range(3)
            )
        )
    strip.putdata(pixels)
    return strip.resize((width, height)).convert("RGBA")


def _contact_shadow(
    canvas_size: tuple[int, int],
    product_size: tuple[int, int],
    offset: tuple[int, int],
) -> Image.Image:
    canvas_width, canvas_height = canvas_size
    product_width, product_height = product_size
    offset_x, offset_y = offset

    mask = Image.new("L", canvas_size, 0)
    draw = ImageDraw.Draw(mask)
    shadow_width = max(20, round(product_width * 0.72))
    shadow_height = max(8, round(product_height * 0.075))
    centre_x = offset_x + product_width // 2
    centre_y = min(
        canvas_height - 1,
        offset_y + round(product_height * 0.94),
    )
    draw.ellipse(
        (
            centre_x - shadow_width // 2,
            centre_y - shadow_height // 2,
            centre_x + shadow_width // 2,
            centre_y + shadow_height // 2,
        ),
        fill=95,
    )
    blur_radius = max(6, round(min(canvas_width, canvas_height) * 0.018))
    mask = mask.filter(ImageFilter.GaussianBlur(blur_radius))
    opacity = _bounded_float(
        "PRODUCT_IMAGE_STUDIO_SHADOW_OPACITY",
        "ALLTECH_PRODUCT_IMAGE_STUDIO_SHADOW_OPACITY",
        0.22,
        0.0,
        0.50,
    )
    mask = mask.point(lambda value: round(value * opacity))
    shadow = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow.putalpha(mask)
    return shadow


def _compose_clean_studio(product: Image.Image) -> Image.Image:
    canvas = _gradient_background()
    fitted, offset = _fit_product(product)
    shadow = _contact_shadow(canvas.size, fitted.size, offset)
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(fitted, offset)
    return canvas


def _compose_transparent(product: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", _canvas_size(), (0, 0, 0, 0))
    fitted, offset = _fit_product(product)
    canvas.alpha_composite(fitted, offset)
    return canvas


def _compose_cinematic(original: Image.Image, product: Image.Image) -> Image.Image:
    canvas_size = _canvas_size()
    backdrop = ImageOps.fit(
        original.convert("RGB"),
        canvas_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    blur_radius = max(10, round(min(canvas_size) * 0.035))
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(blur_radius))
    backdrop = ImageEnhance.Brightness(backdrop).enhance(0.76).convert("RGBA")
    fitted, offset = _fit_product(product)
    backdrop.alpha_composite(fitted, offset)
    return backdrop


def prepare_product_image(
    image: Image.Image,
    *,
    segmenter: Segmenter | None = None,
) -> StudioResult:
    """Prepare a product image for the existing watermark/export pipeline.

    The original image is returned unchanged when the feature is disabled or
    preparation fails. Tests and offline tools can inject a deterministic
    ``segmenter`` without loading an AI model.
    """

    original = image.convert("RGBA")
    if not studio_enabled() or studio_style() == "preserve":
        return StudioResult(original)

    try:
        bounded = _limit_dimensions(original)
        cutout = (segmenter or _default_segmenter)(bounded).convert("RGBA")
        if cutout.size != bounded.size:
            cutout = cutout.resize(bounded.size, Image.Resampling.LANCZOS)

        alpha = _refine_alpha(cutout.getchannel("A"))
        cutout.putalpha(alpha)
        crop_box = _expanded_box(_subject_box(alpha), cutout.size)
        product = cutout.crop(crop_box)

        style = studio_style()
        if style == "transparent":
            prepared = _compose_transparent(product)
            return StudioResult(prepared, output_format="PNG", applied=True)
        if style == "cinematic_blur":
            prepared = _compose_cinematic(bounded, product)
            return StudioResult(prepared, applied=True)

        prepared = _compose_clean_studio(product)
        return StudioResult(prepared, applied=True)
    except Exception:
        logger.exception("Product studio preparation failed; preserving the original upload.")
        return StudioResult(original)


def render_product_upload(
    raw: bytes,
    original_name: str,
    *,
    segmenter: Segmenter | None = None,
) -> tuple[bytes, str, bool]:
    """Return processed upload bytes, a safe filename and whether studio was applied."""

    if not raw or not studio_enabled() or studio_style() == "preserve":
        return raw, original_name, False

    try:
        with Image.open(BytesIO(raw)) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGBA")
        result = prepare_product_image(source, segmenter=segmenter)
        if not result.applied:
            return raw, original_name, False

        stem = Path(original_name or "product").stem or "product"
        output = BytesIO()
        if result.output_format == "PNG":
            filename = f"{stem}-studio.png"
            result.image.save(output, format="PNG", optimize=True)
        else:
            filename = f"{stem}-studio.jpg"
            opaque = Image.new("RGB", result.image.size, (255, 255, 255))
            opaque.paste(result.image, mask=result.image.getchannel("A"))
            opaque.save(
                output,
                format="JPEG",
                quality=97,
                optimize=True,
                progressive=True,
                subsampling=0,
            )
        return output.getvalue(), filename, True
    except Exception:
        logger.exception("Could not render product studio upload; preserving the original.")
        return raw, original_name, False
