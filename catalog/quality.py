from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet

from catalog.models import Product


@dataclass(frozen=True, slots=True)
class CatalogueQualityIssue:
    code: str
    label: str
    weight: int
    severity: str = "warning"


@dataclass(frozen=True, slots=True)
class CatalogueQualityRow:
    product: Product
    score: int
    status: str
    issues: tuple[CatalogueQualityIssue, ...]

    @property
    def issue_count(self) -> int:
        return len(self.issues)


IMAGE_MISSING = CatalogueQualityIssue(
    "image_missing",
    "No customer-visible image",
    22,
    "critical",
)
SHORT_COPY_MISSING = CatalogueQualityIssue(
    "short_copy_missing",
    "Short description is missing or too brief",
    10,
)
DETAIL_COPY_MISSING = CatalogueQualityIssue(
    "detail_copy_missing",
    "Detailed description is missing or too brief",
    12,
)
SKU_MISSING = CatalogueQualityIssue(
    "sku_missing",
    "Product SKU is missing",
    8,
)
BRAND_MISSING = CatalogueQualityIssue(
    "brand_missing",
    "Brand metadata is missing",
    10,
)
GROWTH_DATA_MISSING = CatalogueQualityIssue(
    "growth_data_missing",
    "Feed and condition metadata is missing",
    12,
)
ALT_TEXT_MISSING = CatalogueQualityIssue(
    "alt_text_missing",
    "One or more gallery images have no alt text",
    6,
)
INVALID_COMPARE_PRICE = CatalogueQualityIssue(
    "invalid_compare_price",
    "Comparison price does not exceed the selling price",
    6,
)
VARIANT_SKU_MISSING = CatalogueQualityIssue(
    "variant_sku_missing",
    "One or more active variants have no SKU",
    6,
)
VARIANT_COMPARE_PRICE = CatalogueQualityIssue(
    "variant_compare_price",
    "One or more variant comparison prices are invalid",
    5,
)
VARIANT_STOCK_MISSING = CatalogueQualityIssue(
    "variant_stock_missing",
    "All active tracked variants are out of stock",
    10,
)
BASE_STOCK_MISSING = CatalogueQualityIssue(
    "base_stock_missing",
    "Published tracked product is out of stock",
    10,
)
SERVICE_DURATION_MISSING = CatalogueQualityIssue(
    "service_duration_missing",
    "Service duration is not recorded",
    5,
)
CATEGORY_COPY_MISSING = CatalogueQualityIssue(
    "category_copy_missing",
    "Category description is missing",
    4,
)


# Single authoritative registry of supported quality issue filters.
# Keep this in sync with evaluate_product_quality below.
QUALITY_ISSUES = (
    IMAGE_MISSING,
    SHORT_COPY_MISSING,
    DETAIL_COPY_MISSING,
    SKU_MISSING,
    BRAND_MISSING,
    GROWTH_DATA_MISSING,
    ALT_TEXT_MISSING,
    INVALID_COMPARE_PRICE,
    VARIANT_SKU_MISSING,
    VARIANT_COMPARE_PRICE,
    VARIANT_STOCK_MISSING,
    BASE_STOCK_MISSING,
    SERVICE_DURATION_MISSING,
    CATEGORY_COPY_MISSING,
)


def _growth_data(product: Product):
    try:
        return product.growth_data
    except ObjectDoesNotExist:
        return None


def evaluate_product_quality(product: Product) -> CatalogueQualityRow:
    issues: list[CatalogueQualityIssue] = []
    gallery = [item for item in product.gallery_images.all() if item.image]
    active_variants = [item for item in product.variants.all() if item.is_active]

    if not gallery and not product.image:
        issues.append(IMAGE_MISSING)
    if len((product.short_description or "").strip()) < 40:
        issues.append(SHORT_COPY_MISSING)
    if len((product.description or "").strip()) < 100:
        issues.append(DETAIL_COPY_MISSING)
    if not (product.category.description or "").strip():
        issues.append(CATEGORY_COPY_MISSING)

    if product.kind == Product.KIND_PHYSICAL:
        growth_data = _growth_data(product)
        if growth_data is None:
            issues.append(GROWTH_DATA_MISSING)
        elif not growth_data.brand.strip():
            issues.append(BRAND_MISSING)

        if not product.sku.strip():
            issues.append(SKU_MISSING)
        if product.compare_at_price is not None and product.compare_at_price <= product.price:
            issues.append(INVALID_COMPARE_PRICE)
        if active_variants:
            if any(not variant.sku.strip() for variant in active_variants):
                issues.append(VARIANT_SKU_MISSING)
            if any(
                variant.compare_at_price is not None
                and variant.compare_at_price <= variant.price
                for variant in active_variants
            ):
                issues.append(VARIANT_COMPARE_PRICE)
            tracked = [variant for variant in active_variants if variant.track_inventory]
            if (
                product.is_published
                and tracked
                and all(variant.stock_quantity <= 0 for variant in tracked)
            ):
                issues.append(VARIANT_STOCK_MISSING)
        elif (
            product.is_published
            and product.track_inventory
            and product.stock_quantity <= 0
        ):
            issues.append(BASE_STOCK_MISSING)
    elif product.service_duration_hours is None:
        issues.append(SERVICE_DURATION_MISSING)

    if gallery and any(not (item.alt_text or "").strip() for item in gallery):
        issues.append(ALT_TEXT_MISSING)

    score = max(0, 100 - sum(issue.weight for issue in issues))
    if score >= 85:
        status = "ready"
    elif score >= 60:
        status = "attention"
    else:
        status = "critical"
    return CatalogueQualityRow(
        product=product,
        score=score,
        status=status,
        issues=tuple(issues),
    )


def catalogue_quality_rows(
    products: QuerySet | Iterable[Product] | None = None,
) -> list[CatalogueQualityRow]:
    if products is None:
        products = (
            Product.objects.select_related("category", "growth_data")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )
    return [evaluate_product_quality(product) for product in products]


def catalogue_quality_summary(rows: Iterable[CatalogueQualityRow]) -> dict:
    materialized = list(rows)
    issue_counts = Counter(
        issue.code for row in materialized for issue in row.issues
    )
    issue_labels = {
        issue.code: issue.label for row in materialized for issue in row.issues
    }
    published = [row for row in materialized if row.product.is_published]
    average_score = (
        round(sum(row.score for row in materialized) / len(materialized))
        if materialized
        else 100
    )
    return {
        "total": len(materialized),
        "published": len(published),
        "ready": sum(row.status == "ready" for row in materialized),
        "attention": sum(row.status == "attention" for row in materialized),
        "critical": sum(row.status == "critical" for row in materialized),
        "average_score": average_score,
        "issue_counts": [
            {
                "code": code,
                "label": issue_labels[code],
                "count": count,
            }
            for code, count in issue_counts.most_common()
        ],
    }
