from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from catalog.models import Product
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


PROFILE_FIELDS = (
    "processor_family",
    "processor_generation",
    "ram_capacity",
    "ram_type",
    "storage_capacity",
    "storage_type",
    "screen_size",
    "screen_resolution",
    "graphics",
    "operating_system",
    "battery_health_note",
    "keyboard_condition",
    "accessories_included",
    "condition_notes",
    "delivery_note",
)
BOOLEAN_FIELDS = (
    "touchscreen",
    "charger_included",
    "actual_photos",
    "merchant_enabled",
    "merchant_free_shipping",
)


def _text(row, name):
    return (row.get(name) or "").strip()


def _boolean(value: str):
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _decimal(value: str, field: str):
    if not (value or "").strip():
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except InvalidOperation as exc:
        raise CommandError(f"Invalid decimal for {field}: {value}") from exc


def _integer(value: str, field: str):
    if not (value or "").strip():
        return None
    try:
        return int(value.strip())
    except ValueError as exc:
        raise CommandError(f"Invalid integer for {field}: {value}") from exc


def _datetime(value: str, field: str):
    if not (value or "").strip():
        return None
    parsed = parse_datetime(value.strip())
    if parsed is None:
        raise CommandError(f"Invalid ISO datetime for {field}: {value}")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class Command(BaseCommand):
    help = "Bulk-correct catalogue, feed and inspected product fields from CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--verify-now",
            action="store_true",
            help="Set stock and price verification timestamps to now for imported products.",
        )

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser()
        if not path.exists():
            raise CommandError(f"CSV file not found: {path}")

        changed = skipped = errors = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            self.stdout.write("No CSV rows found.")
            return
        if not {"sku", "slug"}.intersection(rows[0].keys()):
            raise CommandError("CSV must include a sku or slug column.")

        with transaction.atomic():
            for number, row in enumerate(rows, start=2):
                sku = _text(row, "sku")
                slug = _text(row, "slug")
                product_query = Product.objects.all()
                product = None
                if sku:
                    product = product_query.filter(sku__iexact=sku).first()
                if product is None and slug:
                    product = product_query.filter(slug=slug).first()
                if product is None:
                    skipped += 1
                    self.stderr.write(f"Row {number}: product not found for SKU={sku!r}, slug={slug!r}")
                    continue

                try:
                    product_changed = False
                    price = _decimal(_text(row, "price"), "price")
                    compare_at_price = _decimal(_text(row, "compare_at_price"), "compare_at_price")
                    stock_quantity = _integer(_text(row, "stock_quantity"), "stock_quantity")
                    published = _boolean(_text(row, "is_published"))
                    featured = _boolean(_text(row, "is_featured"))
                    for field, value in (
                        ("price", price),
                        ("compare_at_price", compare_at_price),
                        ("stock_quantity", stock_quantity),
                        ("is_published", published),
                        ("is_featured", featured),
                    ):
                        if value is not None and getattr(product, field) != value:
                            setattr(product, field, value)
                            product_changed = True
                    for field in ("short_description", "description", "sku"):
                        value = _text(row, field)
                        if value and getattr(product, field) != value:
                            setattr(product, field, value)
                            product_changed = True
                    if product_changed:
                        product.save()

                    growth, _ = ProductGrowthData.objects.get_or_create(product=product)
                    growth_changed = False
                    for field in ("brand", "gtin", "mpn", "google_product_category", "custom_label_0", "shipping_label"):
                        value = _text(row, field)
                        if value and getattr(growth, field) != value:
                            setattr(growth, field, value)
                            growth_changed = True
                    condition = _text(row, "condition").lower()
                    valid_conditions = {value for value, _ in ProductGrowthData.CONDITION_CHOICES}
                    if condition:
                        if condition not in valid_conditions:
                            raise CommandError(
                                f"Row {number}: condition must be one of {sorted(valid_conditions)}, got {condition!r}"
                            )
                        if growth.condition != condition:
                            growth.condition = condition
                            growth_changed = True
                    if growth_changed:
                        growth.save()

                    profile, _ = ProductCommerceProfile.objects.get_or_create(product=product)
                    profile_changed = False
                    for field in PROFILE_FIELDS:
                        value = _text(row, field)
                        if value and getattr(profile, field) != value:
                            setattr(profile, field, value)
                            profile_changed = True
                    for field in BOOLEAN_FIELDS:
                        value = _boolean(_text(row, field))
                        if value is not None and getattr(profile, field) != value:
                            setattr(profile, field, value)
                            profile_changed = True
                    warranty = _integer(_text(row, "warranty_months"), "warranty_months")
                    if warranty is not None and profile.warranty_months != warranty:
                        profile.warranty_months = max(0, warranty)
                        profile_changed = True
                    shipping = _decimal(_text(row, "merchant_shipping_price"), "merchant_shipping_price")
                    if shipping is not None and profile.merchant_shipping_price != shipping:
                        profile.merchant_shipping_price = shipping
                        profile_changed = True
                    stock_verified = _datetime(_text(row, "stock_confirmed_at"), "stock_confirmed_at")
                    price_verified = _datetime(_text(row, "price_verified_at"), "price_verified_at")
                    if options["verify_now"]:
                        stock_verified = price_verified = timezone.now()
                    for field, value in (
                        ("stock_confirmed_at", stock_verified),
                        ("price_verified_at", price_verified),
                    ):
                        if value is not None and getattr(profile, field) != value:
                            setattr(profile, field, value)
                            profile_changed = True
                    if profile_changed:
                        profile.save()
                    changed += 1
                    self.stdout.write(
                        f"Row {number}: {product.name} — readiness {profile.merchant_readiness_score}%"
                    )
                except CommandError as exc:
                    errors += 1
                    self.stderr.write(str(exc))

            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: all database changes rolled back."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(rows)} rows: {changed} matched, {skipped} skipped, {errors} invalid."
            )
        )
