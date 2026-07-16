from django.core.management.base import BaseCommand

from catalog.models import Product, ProductImage
from catalog.responsive_images import generate_responsive_variants


class Command(BaseCommand):
    help = "Generate proportional responsive WebP derivatives for public product images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count image records without writing derivative files.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild derivatives even when they already exist.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum image records to inspect; 0 means all.",
        )

    def handle(self, *args, **options):
        rows = []
        for product in Product.objects.exclude(image="").exclude(image__isnull=True):
            rows.append((f"Product {product.pk}", product.image))
        for image in ProductImage.objects.exclude(image="").exclude(image__isnull=True):
            rows.append((f"Gallery image {image.pk}", image.image))

        limit = max(0, options["limit"])
        if limit:
            rows = rows[:limit]
        if options["dry_run"]:
            self.stdout.write(f"Image records to inspect: {len(rows)}")
            return

        processed = derivatives = failed = 0
        for label, field_file in rows:
            try:
                names = generate_responsive_variants(
                    field_file,
                    force=options["force"],
                )
                processed += 1
                derivatives += len(names)
                self.stdout.write(f"{label}: {len(names)} derivative(s)")
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"{label}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                "Responsive image generation complete — "
                f"records: {processed}; derivatives: {derivatives}; failed: {failed}."
            )
        )
