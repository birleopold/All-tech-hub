"""Conservative spelling hints for otherwise empty catalogue searches.

Suggestions never silently change the customer query, and they use only
published catalogue facts.
"""
from __future__ import annotations

import re
from difflib import get_close_matches

from catalog.models import Category, Product
from growth.models import ProductGrowthData

_WORDS = re.compile(r"[^\W_]{4,}", re.UNICODE)


def suggested_catalog_query(query: str) -> str | None:
    """Correct a plausible alphabetic typo in real, published product words."""
    raw = (query or "").strip()
    if not 4 <= len(raw) <= 80 or len(raw.split()) > 6:
        return None

    names = Product.objects.filter(is_published=True).order_by(
        "-updated_at"
    ).values_list("name", flat=True)[:2000]
    categories = Category.objects.filter(
        products__is_published=True
    ).distinct().order_by("name").values_list("name", flat=True)[:200]
    brands = ProductGrowthData.objects.filter(
        product__is_published=True
    ).exclude(brand="").values_list("brand", flat=True).distinct()[:200]

    vocabulary = {}
    for name in (*names, *categories, *brands):
        for match in _WORDS.finditer(name or ""):
            word = match.group()
            if 4 <= len(word) <= 24:
                vocabulary.setdefault(word.casefold(), word)

    corrected = []
    changed = False
    for token in raw.split():
        key = token.casefold()
        if key in vocabulary or not token.isalpha() or not 4 <= len(token) <= 24:
            corrected.append(token)
            continue
        matches = get_close_matches(key, vocabulary.keys(), n=1, cutoff=0.78)
        if matches:
            corrected.append(vocabulary[matches[0]])
            changed = True
        else:
            corrected.append(token)
    candidate = " ".join(corrected)
    return candidate if changed and candidate.casefold() != raw.casefold() else None
