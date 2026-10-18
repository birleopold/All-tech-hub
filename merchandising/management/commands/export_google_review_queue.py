"""Export an actionable Google Merchant review queue without changing product facts."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product
from merchandising.models import ProductCommerceProfile


class Command(BaseCommand):
    help = "Create a staff review CSV prioritizing products for free Google listings. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="Destination CSV file")
        parser.add_argument("--limit", type=int, default=0, help="Maximum rows; 0 means all")
        parser.add_argument(
            "--available-only", action="store_true",
            help="Focus on published tracked products with positive current stock",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must not be negative")
        path = Path(options["output"]).expanduser()
        if path.suffix.lower() != ".csv":
            raise CommandError("--output must be a CSV file")
        if path.exists():
            raise CommandError("Output already exists; choose a new filename to preserve earlier evidence")
        products = (
            Product.objects.filter(kind=Product.KIND_PHYSICAL, is_published=True)
            .select_related("category", "commerce_profile", "growth_data")
            .prefetch_related("gallery_images", "variants")
        )
        if options["available_only"]:
            products = products.filter(track_inventory=True, stock_quantity__gt=0)
        rows = []
        counts = Counter()
        for product in products.iterator(chunk_size=100):
            try:
                profile = product.commerce_profile
            except ProductCommerceProfile.DoesNotExist:
                profile = None
            missing = profile.merchant_missing_fields() if profile else ["commercial profile"]
            available = bool(product.track_inventory and product.stock_quantity > 0)
            if not available:
                # A non-stock-tracked product needs manual stock verification.
                missing = list(dict.fromkeys([*missing, "confirm saleable stock"]))
            counts.update(missing)
            rows.append({
                "product_id": product.pk,
                "product_name": product.name,
                "category": product.category.name if product.category_id else "",
                "stock_quantity": product.stock_quantity if product.track_inventory else "",
                "stock_tracked": "yes" if product.track_inventory else "no",
                "merchant_approved": "yes" if profile and profile.merchant_enabled else "no",
                "merchant_score": profile.merchant_readiness_score if profile else 0,
                "missing_checks": "; ".join(missing),
                "review_path": f"/staff/catalogue/products/{product.pk}/commercial-review/",
            })
        # Work on verifiably available products first; among those, resolve
        # near-ready records before records with multiple unresolved claims.
        rows.sort(key=lambda row: (
            row["stock_tracked"] != "yes" or row["stock_quantity"] <= 0,
            -row["merchant_score"], str(row["product_name"]).casefold(), row["product_id"],
        ))
        if options["limit"]:
            rows = rows[:options["limit"]]
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "product_id", "product_name", "category", "stock_quantity",
            "stock_tracked", "merchant_approved", "merchant_score",
            "missing_checks", "review_path",
        ]
        with path.open("x", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(self.style.SUCCESS(
            f"Google review queue exported: {len(rows)} rows to {path}. No products changed."
        ))
