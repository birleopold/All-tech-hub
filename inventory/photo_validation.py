"""Validate mobile product photos; convert iPhone HEIC into supported JPEG."""
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
FORMATS = {
    "image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP",
    "image/heic": "HEIF", "image/heif": "HEIF",
}


class InvalidProductPhoto(ValueError):
    pass


def prepare_product_photo(upload):
    if upload.size <= 0 or upload.size > MAX_PHOTO_BYTES:
        raise InvalidProductPhoto("Each photo must be 12 MB or smaller.")
    mime = (getattr(upload, "content_type", "") or "").lower()
    extension = Path(upload.name).suffix.lower()
    if mime == "application/octet-stream" and extension in {".heic", ".heif"}:
        mime = "image/heic"
    if mime not in FORMATS:
        raise InvalidProductPhoto("Choose JPEG, PNG, WebP or iPhone HEIC photos.")
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            if image.format != FORMATS[mime]:
                raise InvalidProductPhoto("Photo format does not match the uploaded file type.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise InvalidProductPhoto("Photo dimensions are too large.")
            image.load()
            if mime in {"image/heic", "image/heif"}:
                jpeg = BytesIO()
                ImageOps.exif_transpose(image).convert("RGB").save(
                    jpeg, format="JPEG", quality=88, optimize=True
                )
                if jpeg.tell() > MAX_PHOTO_BYTES:
                    raise InvalidProductPhoto("The converted photo exceeds 12 MB.")
                return SimpleUploadedFile(
                    Path(upload.name).stem[:100] + ".jpg",
                    jpeg.getvalue(), content_type="image/jpeg",
                )
    except InvalidProductPhoto:
        raise
    except (OSError, ValueError, RuntimeError, SyntaxError, UnidentifiedImageError) as exc:
        raise InvalidProductPhoto("This photo is damaged or could not be opened.") from exc
    finally:
        upload.seek(0)
    return upload
