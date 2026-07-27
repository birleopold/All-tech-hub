from __future__ import annotations

import csv
import io
from collections import Counter
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from core.audit import log_audit_event
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile, SearchQueryInsight


def _product_available_from_prefetch(product: Product) -> bool:
    active_variants = [variant for variant in product.variants.all() if variant.is_active]
    if active_variants:
        return any(
            (not variant.track_inventory) or int(variant.stock_quantity) > 0
            for variant in active_variants
        )
    return (not product.track_inventory) or int(product.stock_quantity) > 0


def _has_public_image(product: Product) -> bool:
    if product.image:
        return True
    return any(image.image for image in product.gallery_images.all())


@transaction.atomic
def apply_bulk_catalogue_enrichment(*, products, cleaned_data: dict, actor) -> dict:
    now = timezone.now()
    counts = Counter()
    brand = (cleaned_data.get("brand") or "").strip()
    condition = (cleaned_data.get("condition") or "").strip()
    delivery_note = (cleaned_data.get("delivery_note") or "").strip()
    warranty_months = cleaned_data.get("warranty_months")
    shipping_mode = cleaned_data.get("shipping_mode") or ""
    shipping_price = cleaned_data.get("merchant_shipping_price")

    product_list = list(products)
    for product in product_list:
        product_fields: list[str] = []
        growth, growth_created = ProductGrowthData.objects.get_or_create(product=product)
        profile, profile_created = ProductCommerceProfile.objects.get_or_create(product=product)
        if growth_created:
            counts["growth_profiles_created"] += 1
        if profile_created:
            counts["commerce_profiles_created"] += 1

        growth_fields: list[str] = []
        profile_fields: list[str] = []

        if brand and growth.brand != brand:
            growth.brand = brand
            growth_fields.append("brand")
            counts["brands_updated"] += 1
        if condition and growth.condition != condition:
            growth.condition = condition
            growth_fields.append("condition")
            counts["conditions_updated"] += 1

        if cleaned_data.get("generate_missing_sku") and not product.sku.strip():
            product.sku = f"LS-{product.pk:06d}"
            product_fields.append("sku")
            counts["skus_generated"] += 1

        if warranty_months is not None and profile.warranty_months != warranty_months:
            profile.warranty_months = warranty_months
            profile_fields.append("warranty_months")
            counts["warranties_updated"] += 1
        if delivery_note and profile.delivery_note != delivery_note:
            profile.delivery_note = delivery_note
            profile_fields.append("delivery_note")
            counts["delivery_notes_updated"] += 1

        if shipping_mode == "free":
            if not profile.merchant_free_shipping or profile.merchant_shipping_price is not None:
                profile.merchant_free_shipping = True
                profile.merchant_shipping_price = None
                profile_fields.extend(
                    field
                    for field in ("merchant_free_shipping", "merchant_shipping_price")
                    if field not in profile_fields
                )
                counts["shipping_updated"] += 1
        elif shipping_mode == "price":
            if profile.merchant_free_shipping or profile.merchant_shipping_price != shipping_price:
                profile.merchant_free_shipping = False
                profile.merchant_shipping_price = shipping_price
                profile_fields.extend(
                    field
                    for field in ("merchant_free_shipping", "merchant_shipping_price")
                    if field not in profile_fields
                )
                counts["shipping_updated"] += 1

        if cleaned_data.get("confirm_actual_photos"):
            if _has_public_image(product):
                if not profile.actual_photos:
                    profile.actual_photos = True
                    profile_fields.append("actual_photos")
                    counts["actual_photos_confirmed"] += 1
            else:
                counts["actual_photos_skipped"] += 1

        effective_brand = brand or (growth.brand or "").strip()
        if cleaned_data.get("verify_identity"):
            if effective_brand:
                profile.identity_verified_at = now
                profile_fields.append("identity_verified_at")
                counts["identity_verified"] += 1
            else:
                counts["identity_verification_skipped"] += 1

        if cleaned_data.get("verify_condition"):
            if condition or growth.condition:
                profile.condition_verified_at = now
                profile_fields.append("condition_verified_at")
                counts["condition_verified"] += 1
            else:
                counts["condition_verification_skipped"] += 1
        if cleaned_data.get("verify_stock"):
            profile.stock_confirmed_at = now
            profile_fields.append("stock_confirmed_at")
            counts["stock_verified"] += 1
        if cleaned_data.get("verify_price"):
            profile.price_verified_at = now
            profile_fields.append("price_verified_at")
            counts["price_verified"] += 1

        if cleaned_data.get("fill_blank_alt_text"):
            condition_label = growth.get_condition_display() if growth.condition else ""
            descriptor = f" {condition_label.lower()}" if condition_label else ""
            for position, image in enumerate(product.gallery_images.all(), start=1):
                if image.image and not image.alt_text.strip():
                    image.alt_text = (
                        f"{product.name}{descriptor} product image {position}"
                    )[:200]
                    image.save(update_fields=["alt_text"])
                    counts["alt_text_completed"] += 1

        if (
            cleaned_data.get("unpublish_out_of_stock")
            and product.is_published
            and product.track_inventory
            and not _product_available_from_prefetch(product)
        ):
            product.is_published = False
            product_fields.append("is_published")
            counts["products_unpublished"] += 1

        if product_fields:
            product_fields.append("updated_at")
            product.save(update_fields=list(dict.fromkeys(product_fields)))
        if growth_fields:
            growth.save(update_fields=list(dict.fromkeys(growth_fields + ["updated_at"])))
        if profile_fields:
            profile.save(update_fields=list(dict.fromkeys(profile_fields + ["updated_at"])))
        counts["products_processed"] += 1

    log_audit_event(
        actor=actor,
        verb="catalog.bulk_enrichment",
        summary=(
            f"Bulk-enriched {counts['products_processed']} catalogue products; "
            f"brands {counts['brands_updated']}, conditions {counts['conditions_updated']}, "
            f"SKUs {counts['skus_generated']}, alt text {counts['alt_text_completed']}."
        ),
    )
    return dict(counts)


def merchant_readiness_snapshot(*, row_limit: int = 12) -> dict:
    products = list(
        Product.objects.filter(kind=Product.KIND_PHYSICAL)
        .select_related("category", "growth_data", "commerce_profile")
        .prefetch_related("gallery_images", "variants")
        .order_by("name", "pk")
    )
    missing_counts: Counter[str] = Counter()
    rows = []
    profile_count = 0
    enabled_count = 0
    ready_count = 0
    enabled_blocked = 0
    score_total = 0

    for product in products:
        try:
            profile = product.commerce_profile
        except ObjectDoesNotExist:
            profile = None
        if profile is None:
            score = 0
            missing = ["commercial profile"]
            merchant_enabled = False
        else:
            profile_count += 1
            score = profile.merchant_readiness_score
            missing = profile.merchant_missing_fields()
            merchant_enabled = profile.merchant_enabled
            if merchant_enabled:
                enabled_count += 1
            if not missing:
                ready_count += 1
            if merchant_enabled and missing:
                enabled_blocked += 1
        score_total += score
        missing_counts.update(missing)
        rows.append(
            {
                "product": product,
                "score": score,
                "missing": missing,
                "merchant_enabled": merchant_enabled,
                "ready": not missing,
            }
        )

    rows.sort(key=lambda row: (row["score"], row["product"].name.casefold()))
    total = len(products)
    return {
        "total_products": total,
        "profiles": profile_count,
        "enabled": enabled_count,
        "ready": ready_count,
        "enabled_blocked": enabled_blocked,
        "average_score": round(score_total / total) if total else 100,
        "strict_mode": bool(getattr(settings, "MERCHANT_STRICT_READINESS", False)),
        "missing_counts": [
            {"label": label, "count": count}
            for label, count in missing_counts.most_common(12)
        ],
        "priority_rows": rows[: max(0, row_limit)],
    }


def _normalised_headers(fieldnames) -> dict[str, str]:
    return {
        (name or "").strip().casefold().replace("_", " "): name
        for name in fieldnames or []
    }


def _value(row: dict, headers: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        source = headers.get(alias)
        if source:
            return (row.get(source) or "").strip()
    return ""


def _parse_nonnegative_integer(value: str) -> int:
    if not value:
        return 0
    parsed = int(float(value.replace(",", "")))
    return max(0, parsed)


def _parse_decimal(value: str, *, percentage: bool = False) -> Decimal:
    if not value:
        return Decimal("0")
    cleaned = value.replace(",", "").strip()
    is_percent = cleaned.endswith("%")
    cleaned = cleaned.rstrip("%").strip()
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc
    if percentage or is_percent:
        parsed = parsed / Decimal("100")
    return max(Decimal("0"), parsed)


@transaction.atomic
def import_search_console_csv(*, uploaded_file, date_start=None, date_end=None) -> dict:
    try:
        text = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The CSV must use UTF-8 encoding.") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = _normalised_headers(reader.fieldnames)
    query_aliases = ("top queries", "query", "queries", "search query")
    if not any(alias in headers for alias in query_aliases):
        raise ValueError(
            "The CSV has no Query or Top queries column. Export the Queries table "
            "from the Google Search Console Performance report."
        )

    created = 0
    updated = 0
    skipped = 0
    for row_number, row in enumerate(reader, start=2):
        query = _value(row, headers, query_aliases)[:500]
        page = _value(row, headers, ("top pages", "page", "pages", "landing page"))[:200]
        if not query:
            skipped += 1
            continue
        try:
            clicks = _parse_nonnegative_integer(
                _value(row, headers, ("clicks", "click"))
            )
            impressions = _parse_nonnegative_integer(
                _value(row, headers, ("impressions", "impression"))
            )
            ctr = _parse_decimal(
                _value(row, headers, ("ctr", "click through rate", "click-through rate")),
                percentage=True,
            )
            position = _parse_decimal(
                _value(row, headers, ("position", "average position", "avg position"))
            )
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {exc}") from exc

        _, was_created = SearchQueryInsight.objects.update_or_create(
            query=query,
            page=page,
            date_start=date_start,
            date_end=date_end,
            defaults={
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "skipped": skipped}


def search_opportunity_rows(*, limit: int = 20) -> list[dict]:
    latest_rows = SearchQueryInsight.objects.order_by(
        "-date_end", "-imported_at", "-impressions", "position"
    )[:2000]
    seen = set()
    opportunities = []
    for insight in latest_rows:
        key = (insight.query.casefold(), insight.page.casefold())
        if key in seen:
            continue
        seen.add(key)
        impressions = int(insight.impressions or 0)
        position = float(insight.position or 0)
        ctr = float(insight.ctr or 0)
        if impressions < 10 or position <= 0 or position > 30:
            continue
        if position <= 3 and ctr >= 0.08:
            continue
        if position <= 10:
            stage = "Page-one opportunity"
            weight = 1.5
        elif position <= 20:
            stage = "Near page one"
            weight = 1.2
        else:
            stage = "Growing visibility"
            weight = 1.0
        score = impressions * max(0.05, 1 - min(ctr, 1)) * weight
        opportunities.append(
            {
                "insight": insight,
                "stage": stage,
                "score": round(score, 1),
                "ctr_percent": round(ctr * 100, 2),
            }
        )
    opportunities.sort(key=lambda row: (-row["score"], row["insight"].position))
    return opportunities[: max(0, limit)]
