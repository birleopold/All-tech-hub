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
VERIFICATION_FIELDS = (
    "identity_verified_at",
    "condition_verified_at",
    "stock_confirmed_at",
    "price_verified_at",
)


def _text(row, name):
    return (row.get(name) or "").strip()


def _boolean(value: str):
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    if normalized:
        raise CommandError(f"Invalid boolean value: {value}")
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
            help="Mark imported identity, condition, price and stock as checked now.",
        )

    def _find_product(self, row):
        sku = _text(row, "sku")
        slug = _text(row, "slug")
        product = Product.objects.filter(sku__iexact=sku).first() if sku else None
        if product is None and slug:
            product = Product.objects.filter(slug=slug).first()
        return product, sku, slug

    def _parse_row(self, row, number):
        condition = _text(row, "condition").lower()
        valid_conditions = {value for value, _ in ProductGrowthData.CONDITION_CHOICES}
        if condition and condition not in valid_conditions:
            raise CommandError(
                f"Row {number}: condition must be one of {sorted(valid_conditions)}, got {condition!r}"
            )
        parsed = {
            "price": _decimal(_text(row, "price"), "price"),
            "compare_at_price": _decimal(_text(row, "compare_at_price"), "compare_at_price"),
            "stock_quantity": _integer(_text(row, "stock_quantity"), "stock_quantity"),
            "is_published": _boolean(_text(row, "is_published")),
            "is_featured": _boolean(_text(row, "is_featured")),
            "condition": condition,
            "warranty_months": _integer(_text(row, "warranty_months"), "warranty_months"),
            "merchant_shipping_price": _decimal(
                _text(row, "merchant_shipping_price"),
                "merchant_shipping_price",
            ),
        }
        for field in BOOLEAN_FIELDS:
            parsed[field] = _boolean(_text(row, field))
        for field in VERIFICATION_FIELDS:
            parsed[field] = _datetime(_text(row, field), field)
        return parsed

    def _apply_row(self, product, row, parsed, verify_now):
        product_changed = False
        for field in ("price", "compare_at_price", "stock_quantity", "is_published", "is_featured"):
            value = parsed[field]
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
        for field in (
            "brand",
            "gtin",
            "mpn",
            "google_product_category",
            "custom_label_0",
            "shipping_label",
        ):
            value = _text(row, field)
            if value and getattr(growth, field) != value:
                setattr(growth, field, value)
                growth_changed = True
        if parsed["condition"] and growth.condition != parsed["condition"]:
            growth.condition = parsed["condition"]
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
            value = parsed[field]
            if value is not None and getattr(profile, field) != value:
                setattr(profile, field, value)
                profile_changed = True
        warranty = parsed["warranty_months"]
        if warranty is not None and profile.warranty_months != max(0, warranty):
            profile.warranty_months = max(0, warranty)
            profile_changed = True
        shipping = parsed["merchant_shipping_price"]
        if shipping is not None and profile.merchant_shipping_price != shipping:
            profile.merchant_shipping_price = shipping
            profile_changed = True

        verification_values = {field: parsed[field] for field in VERIFICATION_FIELDS}
        if verify_now:
            now = timezone.now()
            verification_values = {field: now for field in VERIFICATION_FIELDS}
        for field, value in verification_values.items():
            if value is not None and getattr(profile, field) != value:
                setattr(profile, field, value)
                profile_changed = True
        if profile_changed:
            profile.save()
        return profile

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser()
        if not path.exists():
            raise CommandError(f"CSV file not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            self.stdout.write("No CSV rows found.")
            return
        if not {"sku", "slug"}.intersection(rows[0].keys()):
            raise CommandError("CSV must include a sku or slug column.")

        changed = skipped = errors = 0
        with transaction.atomic():
            for number, row in enumerate(rows, start=2):
                product, sku, slug = self._find_product(row)
                if product is None:
                    skipped += 1
                    self.stderr.write(
                        f"Row {number}: product not found for SKU={sku!r}, slug={slug!r}"
                    )
                    continue
                try:
                    parsed = self._parse_row(row, number)
                    with transaction.atomic():
                        profile = self._apply_row(
                            product,
                            row,
                            parsed,
                            options["verify_now"],
                        )
                    changed += 1
                    self.stdout.write(
                        f"Row {number}: {product.name} — readiness {profile.merchant_readiness_score}%"
                    )
                except CommandError as exc:
                    errors += 1
                    self.stderr.write(str(exc))

            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING("Dry run: all database changes rolled back.")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(rows)} rows: {changed} matched, {skipped} skipped, {errors} invalid."
            )
        )
