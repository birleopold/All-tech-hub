from __future__ import annotations

import csv
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import Product
from merchandising.models import ProductCommerceProfile


class Command(BaseCommand):
    help = "Audit product condition, identifiers, images, stock freshness and Merchant readiness."

    def add_arguments(self, parser):
        parser.add_argument("--csv", dest="csv_path", help="Optional CSV output path.")
        parser.add_argument(
            "--stale-days",
            type=int,
            default=14,
            help="Days after which stock or price verification is treated as stale.",
        )
        parser.add_argument(
            "--only-published",
            action="store_true",
            help="Audit only public products.",
        )
        parser.add_argument(
            "--fail-on-incomplete",
            action="store_true",
            help="Return a command error when any audited product is incomplete.",
        )

    def handle(self, *args, **options):
        queryset = (
            Product.objects.filter(kind=Product.KIND_PHYSICAL)
            .select_related("category", "growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )
        if options["only_published"]:
            queryset = queryset.filter(is_published=True)

        stale_before = timezone.now() - timezone.timedelta(days=max(1, options["stale_days"]))
        rows = []
        issue_counts: dict[str, int] = {}
        ready = 0

        for product in queryset:
            try:
                metadata = product.growth_data
            except ObjectDoesNotExist:
                metadata = None
            try:
                profile = product.commerce_profile
            except ObjectDoesNotExist:
                profile = None

            issues: list[str] = []
            brand = (getattr(metadata, "brand", "") or "").strip()
            condition = (getattr(metadata, "condition", "") or "").strip()
            gtin = (getattr(metadata, "gtin", "") or "").strip()
            mpn = (getattr(metadata, "mpn", "") or "").strip()
            image = product.primary_display_image
            image_name = getattr(image, "name", "") if image else ""

            if not brand:
                issues.append("missing brand")
            if not condition:
                issues.append("missing condition")
            if not gtin and not (brand and mpn):
                issues.append("missing GTIN or brand+MPN")
            if not image:
                issues.append("missing image")
            if image_name and image_name.rsplit("/", 1)[-1].lower().startswith(("wm_wm_", "wm-wm-")):
                issues.append("repeated watermark filename")
            if not product.short_description and not product.description:
                issues.append("missing description")
            if product.track_inventory and product.stock_quantity == 0 and not product.has_sellable_variants():
                issues.append("out of stock")
            if profile is None:
                issues.append("missing commercial profile")
                readiness = 0
                merchant_enabled = False
                stock_verified = ""
                price_verified = ""
            else:
                merchant_enabled = profile.merchant_enabled
                readiness = profile.merchant_readiness_score
                stock_verified = profile.stock_confirmed_at
                price_verified = profile.price_verified_at
                if profile.stock_confirmed_at and profile.stock_confirmed_at < stale_before:
                    issues.append("stale stock verification")
                if profile.price_verified_at and profile.price_verified_at < stale_before:
                    issues.append("stale price verification")
                for missing in profile.merchant_missing_fields():
                    label = f"merchant: {missing}"
                    if label not in issues:
                        issues.append(label)
                if profile.is_merchant_ready:
                    ready += 1

            for issue in issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

            rows.append(
                {
                    "id": product.pk,
                    "sku": product.sku,
                    "slug": product.slug,
                    "product": product.name,
                    "published": product.is_published,
                    "category": product.category.name,
                    "brand": brand,
                    "condition": condition,
                    "gtin": gtin,
                    "mpn": mpn,
                    "stock": product.stock_quantity,
                    "image": image_name,
                    "merchant_enabled": merchant_enabled,
                    "merchant_readiness": readiness,
                    "stock_verified_at": stock_verified,
                    "price_verified_at": price_verified,
                    "issues": "; ".join(issues),
                }
            )

        self.stdout.write(f"Audited {len(rows)} physical products; {ready} are strict-Merchant ready.")
        for issue, count in sorted(issue_counts.items(), key=lambda item: (-item[1], item[0])):
            self.stdout.write(f"  {count:>4}  {issue}")

        csv_path = options.get("csv_path")
        if csv_path:
            destination = Path(csv_path).expanduser()
            destination.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = list(rows[0].keys()) if rows else [
                "id", "sku", "slug", "product", "published", "category", "brand",
                "condition", "gtin", "mpn", "stock", "image", "merchant_enabled",
                "merchant_readiness", "stock_verified_at", "price_verified_at", "issues",
            ]
            with destination.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"Wrote {destination}"))

        incomplete = sum(1 for row in rows if row["issues"])
        if options["fail_on_incomplete"] and incomplete:
            self.stderr.write(self.style.ERROR(f"{incomplete} product(s) require catalogue review."))
            raise SystemExit(1)
