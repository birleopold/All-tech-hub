import re
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from catalog.models import Product, ProductImage
from catalog.watermarks import WATERMARK_PREFIX

DIGEST_PATTERN = re.compile(r"([0-9a-f]{12})(?:_[A-Za-z0-9]+)?$")
ARCHIVE_DIGEST_PATTERN = re.compile(r"-([0-9a-f]{16})$")


def _archive_root() -> Path:
    configured = getattr(settings, "PRIVATE_MEDIA_ROOT", None)
    if configured:
        return Path(configured) / "product_originals"
    return Path(settings.BASE_DIR) / "private_media" / "product_originals"


def _public_digest(image_name: str) -> str | None:
    stem = Path(image_name or "").stem
    if not stem.startswith(WATERMARK_PREFIX):
        return None
    match = DIGEST_PATTERN.search(stem)
    return match.group(1) if match else None


def _find_archived_original(image_name: str) -> Path | None:
    digest = _public_digest(image_name)
    root = _archive_root()
    if not digest or not root.exists():
        return None

    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        match = ARCHIVE_DIGEST_PATTERN.search(candidate.stem)
        if match and match.group(1).startswith(digest):
            return candidate
    return None


def _original_upload_name(archive_path: Path) -> str:
    stem = ARCHIVE_DIGEST_PATTERN.sub("", archive_path.stem) or "product"
    return f"{stem}{archive_path.suffix.lower()}"


class Command(BaseCommand):
    help = (
        "Rebuild already-watermarked product and gallery images from their private "
        "originals, applying the current enhancement and watermark settings once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count safely restorable images without changing public files.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of images to rebuild; 0 means no limit.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = max(0, options["limit"])
        candidates = []

        for product in Product.objects.exclude(image="").exclude(image__isnull=True):
            candidates.append((product, "image", f"Product {product.pk}"))

        for image in ProductImage.objects.exclude(image="").exclude(image__isnull=True):
            candidates.append((image, "image", f"Gallery image {image.pk}"))

        restorable = []
        missing_original = 0
        for instance, field_name, label in candidates:
            field_file = getattr(instance, field_name)
            if not Path(field_file.name).name.startswith(WATERMARK_PREFIX):
                continue
            archive_path = _find_archived_original(field_file.name)
            if archive_path:
                restorable.append((instance, field_name, label, archive_path))
            else:
                missing_original += 1

        if limit:
            restorable = restorable[:limit]

        if dry_run:
            self.stdout.write(f"Images safely restorable: {len(restorable)}")
            self.stdout.write(f"Watermarked images missing originals: {missing_original}")
            return

        processed = failed = 0
        for instance, field_name, label, archive_path in restorable:
            old_field = getattr(instance, field_name)
            old_name = old_field.name
            storage = old_field.storage
            try:
                original_bytes = archive_path.read_bytes()
                replacement = ContentFile(
                    original_bytes,
                    name=_original_upload_name(archive_path),
                )
                setattr(instance, field_name, replacement)
                instance.save(update_fields=[field_name])
                new_name = getattr(instance, field_name).name
                if old_name and old_name != new_name:
                    storage.delete(old_name)
                processed += 1
                self.stdout.write(self.style.SUCCESS(f"Reprocessed {label}"))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"Could not reprocess {label}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Reprocessing complete — processed: {processed}; failed: {failed}; "
                f"missing originals: {missing_original}."
            )
        )
