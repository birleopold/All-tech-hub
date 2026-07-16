from django.core.management.base import BaseCommand

from catalog.models import Product, ProductImage
from catalog.responsive_images import (
    generate_responsive_variants,
    purge_responsive_name,
)
from catalog.watermarks import WATERMARK_PREFIX, watermark_stored_model_image


class Command(BaseCommand):
    help = (
        "Watermark existing public product and gallery images. "
        "Original files are archived privately before replacement."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count images that need watermarking without changing files.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reprocess images whose filenames already begin with wm_.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of images to process; 0 means no limit.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        limit = max(0, options["limit"])
        candidates = []

        for product in Product.objects.exclude(image="").exclude(image__isnull=True):
            candidates.append((product, "image", f"Product {product.pk}"))

        for image in ProductImage.objects.exclude(image="").exclude(image__isnull=True):
            candidates.append((image, "image", f"Gallery image {image.pk}"))

        pending = []
        for instance, field_name, label in candidates:
            field_file = getattr(instance, field_name)
            is_watermarked = field_file.name.rsplit("/", 1)[-1].startswith(
                WATERMARK_PREFIX
            )
            if force or not is_watermarked:
                pending.append((instance, field_name, label))

        if limit:
            pending = pending[:limit]

        if dry_run:
            self.stdout.write(f"Images requiring watermarking: {len(pending)}")
            return

        processed = failed = 0
        for instance, field_name, label in pending:
            old_field = getattr(instance, field_name)
            old_name = old_field.name
            storage = old_field.storage
            changed = watermark_stored_model_image(
                instance,
                field_name,
                force=force,
            )
            if changed:
                purge_responsive_name(storage, old_name)
                generate_responsive_variants(getattr(instance, field_name), force=True)
                processed += 1
                self.stdout.write(self.style.SUCCESS(f"Watermarked {label}"))
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"Could not watermark {label}"))

        skipped = max(0, len(candidates) - len(pending))
        self.stdout.write(
            self.style.SUCCESS(
                f"Watermarking complete — processed: {processed}; "
                f"already watermarked: {skipped}; failed: {failed}."
            )
        )
