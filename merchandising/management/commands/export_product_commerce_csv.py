from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import Product


IMPORT_FIELDS = (
    "sku",
    "slug",
    "brand",
    "condition",
    "gtin",
    "mpn",
    "price",
    "compare_at_price",
    "stock_quantity",
    "is_published",
    "is_featured",
    "short_description",
    "description",
    "processor_family",
    "processor_generation",
    "ram_capacity",
    "ram_type",
    "storage_capacity",
    "storage_type",
    "screen_size",
    "screen_resolution",
    "touchscreen",
    "graphics",
    "operating_system",
    "battery_health_note",
    "keyboard_condition",
    "charger_included",
    "accessories_included",
    "warranty_months",
    "condition_notes",
    "actual_photos",
    "delivery_note",
    "identity_verified_at",
    "condition_verified_at",
    "stock_confirmed_at",
    "price_verified_at",
    "merchant_enabled",
    "merchant_shipping_price",
    "merchant_free_shipping",
    "google_product_category",
    "custom_label_0",
    "shipping_label",
)

REVIEW_FIELDS = (
    "product_name",
    "category",
    "product_url",
    "available_to_sell",
    "has_public_image",
    "active_variant_count",
    "variant_stock_total",
    "readiness_score",
    "missing_fields",
    "review_status",
    "review_notes",
)

EXPORT_FIELDS = IMPORT_FIELDS[:2] + REVIEW_FIELDS + IMPORT_FIELDS[2:]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.isoformat()
    return str(value)


def _related(product, name):
    try:
        return getattr(product, name)
    except ObjectDoesNotExist:
        return None


def _active_variants(product):
    return [variant for variant in product.variants.all() if variant.is_active]


def _available_to_sell(product, active_variants):
    if active_variants:
        return any(
            (not variant.track_inventory) or int(variant.stock_quantity) > 0
            for variant in active_variants
        )
    return (not product.track_inventory) or int(product.stock_quantity) > 0


def _variant_stock_total(active_variants):
    tracked = [variant for variant in active_variants if variant.track_inventory]
    if not tracked:
        return None
    return sum(int(variant.stock_quantity) for variant in tracked)


def _has_public_image(product):
    if product.image:
        return True
    return any(bool(image.image) for image in product.gallery_images.all())


class Command(BaseCommand):
    help = (
        "Export physical products to a review-ready CSV that can be edited and "
        "passed back to import_product_commerce_csv."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="var/product-commerce-review.csv",
            help="CSV path to create. Parent directories are created automatically.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=30,
            help="Maximum products to export. Use 0 to export every matching product.",
        )
        parser.add_argument(
            "--include-unpublished",
            action="store_true",
            help="Include unpublished physical products.",
        )
        parser.add_argument(
            "--in-stock-only",
            action="store_true",
            help="Export only products currently available to sell.",
        )
        parser.add_argument(
            "--order",
            choices=("priority", "name", "updated"),
            default="priority",
            help="priority = featured and available products first.",
        )

    def _row(self, product):
        growth = _related(product, "growth_data")
        profile = _related(product, "commerce_profile")
        active_variants = _active_variants(product)
        available = _available_to_sell(product, active_variants)
        has_image = _has_public_image(product)

        if profile is None:
            readiness_score = 0
            missing = ["commercial profile"]
        else:
            readiness_score = profile.merchant_readiness_score
            missing = profile.merchant_missing_fields()

        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        row = {
            "sku": product.sku,
            "slug": product.slug,
            "product_name": product.name,
            "category": str(product.category),
            "product_url": f"{base_url}{product.get_absolute_url()}",
            "available_to_sell": available,
            "has_public_image": has_image,
            "active_variant_count": len(active_variants),
            "variant_stock_total": _variant_stock_total(active_variants),
            "readiness_score": readiness_score,
            "missing_fields": "; ".join(missing),
            "review_status": "",
            "review_notes": "",
            "brand": getattr(growth, "brand", ""),
            "condition": getattr(growth, "condition", ""),
            "gtin": getattr(growth, "gtin", ""),
            "mpn": getattr(growth, "mpn", ""),
            "price": product.price,
            "compare_at_price": product.compare_at_price,
            "stock_quantity": product.stock_quantity,
            "is_published": product.is_published,
            "is_featured": product.is_featured,
            "short_description": product.short_description,
            "description": product.description,
            "processor_family": getattr(profile, "processor_family", ""),
            "processor_generation": getattr(profile, "processor_generation", ""),
            "ram_capacity": getattr(profile, "ram_capacity", ""),
            "ram_type": getattr(profile, "ram_type", ""),
            "storage_capacity": getattr(profile, "storage_capacity", ""),
            "storage_type": getattr(profile, "storage_type", ""),
            "screen_size": getattr(profile, "screen_size", ""),
            "screen_resolution": getattr(profile, "screen_resolution", ""),
            "touchscreen": getattr(profile, "touchscreen", None),
            "graphics": getattr(profile, "graphics", ""),
            "operating_system": getattr(profile, "operating_system", ""),
            "battery_health_note": getattr(profile, "battery_health_note", ""),
            "keyboard_condition": getattr(profile, "keyboard_condition", ""),
            "charger_included": getattr(profile, "charger_included", None),
            "accessories_included": getattr(profile, "accessories_included", ""),
            "warranty_months": getattr(profile, "warranty_months", 0),
            "condition_notes": getattr(profile, "condition_notes", ""),
            "actual_photos": getattr(profile, "actual_photos", False),
            "delivery_note": getattr(profile, "delivery_note", ""),
            "identity_verified_at": getattr(profile, "identity_verified_at", None),
            "condition_verified_at": getattr(profile, "condition_verified_at", None),
            "stock_confirmed_at": getattr(profile, "stock_confirmed_at", None),
            "price_verified_at": getattr(profile, "price_verified_at", None),
            "merchant_enabled": getattr(profile, "merchant_enabled", False),
            "merchant_shipping_price": getattr(
                profile, "merchant_shipping_price", None
            ),
            "merchant_free_shipping": getattr(
                profile, "merchant_free_shipping", False
            ),
            "google_product_category": getattr(
                growth, "google_product_category", ""
            ),
            "custom_label_0": getattr(growth, "custom_label_0", ""),
            "shipping_label": getattr(growth, "shipping_label", ""),
        }
        return {field: _cell(row.get(field)) for field in EXPORT_FIELDS}, available

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 0:
            raise CommandError("--limit must be 0 or a positive integer.")

        queryset = (
            Product.objects.filter(kind=Product.KIND_PHYSICAL)
            .select_related("category", "growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants")
        )
        if not options["include_unpublished"]:
            queryset = queryset.filter(is_published=True)

        prepared = []
        for product in queryset:
            row, available = self._row(product)
            if options["in_stock_only"] and not available:
                continue
            prepared.append((product, row, available))

        if options["order"] == "name":
            prepared.sort(key=lambda item: item[0].name.casefold())
        elif options["order"] == "updated":
            prepared.sort(
                key=lambda item: (item[0].updated_at, item[0].name.casefold()),
                reverse=True,
            )
        else:
            prepared.sort(
                key=lambda item: (
                    not item[0].is_featured,
                    not item[2],
                    -int(item[0].stock_quantity),
                    -item[0].updated_at.timestamp(),
                    item[0].name.casefold(),
                )
            )

        if limit:
            prepared = prepared[:limit]

        path = Path(options["output"]).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
            writer.writeheader()
            for _, row, _ in prepared:
                writer.writerow(row)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(prepared)} product review rows to {path}."
            )
        )
        self.stdout.write(
            "Review factual fields, run import_product_commerce_csv --dry-run, "
            "then apply approved rows with --verify-now."
        )
