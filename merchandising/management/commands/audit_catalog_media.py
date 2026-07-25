from __future__ import annotations

import hashlib
from collections import defaultdict

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from catalog.models import Product


class Command(BaseCommand):
    help = "Report repeated watermark prefixes, missing files and duplicate product-image content."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--skip-hashes",
            action="store_true",
            help="Only inspect names and storage existence; do not read image bytes.",
        )

    def handle(self, *args, **options):
        products = Product.objects.prefetch_related("gallery_images").order_by("pk")
        if options["limit"] > 0:
            products = products[: options["limit"]]

        records = []
        for product in products:
            if product.image:
                records.append((product, "primary", product.image.name))
            for gallery in product.gallery_images.all():
                if gallery.image:
                    records.append((product, f"gallery:{gallery.pk}", gallery.image.name))

        missing = []
        repeated = []
        hashes: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for product, role, name in records:
            basename = name.rsplit("/", 1)[-1].lower()
            if basename.startswith(("wm_wm_", "wm-wm-")) or basename.count("wm_") > 1:
                repeated.append((product.name, role, name))
            if not default_storage.exists(name):
                missing.append((product.name, role, name))
                continue
            if options["skip_hashes"]:
                continue
            digest = hashlib.sha256()
            try:
                with default_storage.open(name, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                hashes[digest.hexdigest()].append((product.name, role, name))
            except OSError as exc:
                missing.append((product.name, role, f"{name} ({exc})"))

        duplicates = [items for items in hashes.values() if len(items) > 1]
        self.stdout.write(
            f"Audited {len(records)} product image references: "
            f"{len(missing)} missing, {len(repeated)} repeated watermark names, "
            f"{len(duplicates)} duplicate-content groups."
        )
        if repeated:
            self.stdout.write(self.style.WARNING("Repeated watermark filenames:"))
            for product, role, name in repeated:
                self.stdout.write(f"  {product} [{role}] {name}")
        if missing:
            self.stdout.write(self.style.ERROR("Missing or unreadable files:"))
            for product, role, name in missing:
                self.stdout.write(f"  {product} [{role}] {name}")
        if duplicates:
            self.stdout.write(self.style.WARNING("Duplicate image content:"))
            for group in duplicates:
                self.stdout.write("  Group:")
                for product, role, name in group:
                    self.stdout.write(f"    {product} [{role}] {name}")
