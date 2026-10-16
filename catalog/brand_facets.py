"""Consistent, read-only brand labels for storefront and staff diagnostics.

Do not silently rewrite supplier/product identity: spelling corrections remain a
staff decision. This helper only merges case variants in public filters.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

# Keep familiar manufacturer capitalization without imposing it on stored data.
PREFERRED_LABELS = {
    "acer": "Acer", "apple": "Apple", "asus": "ASUS", "canon": "Canon",
    "dell": "Dell", "epson": "Epson", "hp": "HP", "huawei": "Huawei",
    "lenovo": "Lenovo", "lg": "LG", "logitech": "Logitech",
    "microsoft": "Microsoft", "msi": "MSI", "samsung": "Samsung",
    "sony": "Sony", "tecno": "TECNO", "toshiba": "Toshiba",
    "xiaomi": "Xiaomi",
}


def grouped_brand_rows(
    rows: Iterable[Mapping[str, object]], *, limit: int | None = 18
) -> list[dict]:
    """Sum product counts for equivalent brand spellings and retain edit clues.

    Rows are already aggregated per exact brand label by the database. A
    ProductGrowthData record belongs to one product, so these counts can be
    summed without double-counting products.
    """
    groups: dict[str, dict] = {}
    for row in rows:
        raw = str(row.get("brand") or "")
        stripped = raw.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        count = int(row.get("product_count") or 0)
        group = groups.setdefault(key, {"product_count": 0, "variants": {}})
        group["product_count"] += count
        group["variants"][raw] = group["variants"].get(raw, 0) + count

    result: list[dict] = []
    for key, group in groups.items():
        variants = group["variants"]
        preferred = PREFERRED_LABELS.get(key)
        if preferred is None:
            preferred = sorted(
                variants, key=lambda v: (-variants[v], v.strip().casefold(), v)
            )[0].strip()
        result.append(
            {
                "brand": preferred,
                "product_count": group["product_count"],
                "variants": [
                    {
                        "brand": raw.strip(),
                        "product_count": count,
                        "extra_spaces": raw != raw.strip(),
                    }
                    for raw, count in sorted(
                        variants.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
                    )
                ],
            }
        )

    result.sort(key=lambda row: (-row["product_count"], row["brand"].casefold()))
    return result if limit is None else result[:limit]
