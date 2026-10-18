"""Concise Uganda-specific SEO copy for real storefront departments.

Copy is intentionally conservative: no invented brand selection, stock counts,
delivery speed, payment outcome, ratings or manufacturing authenticity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.seo import clean_text

@dataclass(frozen=True)
class CategorySearchCopy:
    title: str
    description: str
    heading: str

# Titles are concise rather than constrained by an arbitrary Google character
# limit. Google chooses title links and snippets based on each query.
CATEGORY_SEARCH_COPY = {
    "laptops": CategorySearchCopy(
        "Buy Laptops Online in Uganda | Leosoft UG",
        "Browse laptops in Uganda for students, offices and everyday work. Compare available configurations, prices and condition at Leosoft UG.",
        "Laptops in Uganda",
    ),
    "desktops": CategorySearchCopy(
        "Desktop Computers & All-in-One PCs Uganda | Leosoft",
        "Explore desktop computers and all-in-one PCs for home or office in Uganda. Compare recorded specifications, pricing and availability at Leosoft UG.",
        "Desktop Computers in Uganda",
    ),
    "networking": CategorySearchCopy(
        "Wi-Fi Routers & Networking Equipment Uganda | Leosoft",
        "Explore Wi-Fi routers, switches and networking accessories in Uganda. Compare options and ask Leosoft UG about office networking and installation.",
        "Networking Equipment & Wi-Fi",
    ),
    "printers": CategorySearchCopy(
        "Printers, Scanners & Ink Supplies Uganda | Leosoft",
        "Explore printers, scanners and printing accessories in Uganda. Browse available products and request a quotation for home or office at Leosoft UG.",
        "Printers & Scanners in Uganda",
    ),
    "storage": CategorySearchCopy(
        "SSD, Hard Drives & Computer Storage Uganda | Leosoft",
        "Shop SSDs, hard drives and storage accessories in Uganda. Compare capacity, compatibility and prices before requesting your order at Leosoft UG.",
        "Computer Storage & SSDs",
    ),
    "accessories": CategorySearchCopy(
        "Computer Accessories & Tech Gadgets Uganda | Leosoft",
        "Explore mice, keyboards, chargers and other computer accessories in Uganda. Check product details, price and availability at Leosoft UG.",
        "Computer Accessories in Uganda",
    ),
}

# Match only categories that clearly belong to the named department. Slugs
# remain unchanged (links and indexing signals must not break).
_KEYWORDS = (
    ("laptops", re.compile(r"\b(laptops?|notebooks?)\b")),
    ("desktops", re.compile(r"\b(desktops?|all[ -]?in[ -]?one(?:s)?|a[ -]?i[ -]?o|workstations?)\b")),
    ("networking", re.compile(r"\b(network(?:ing)?|routers?|wi[ -]?fi|switches|lan|access[ -]?points?)\b")),
    ("printers", re.compile(r"\b(printers?|scanners?|printing|ink|toners?)\b")),
    ("storage", re.compile(r"\b(storage|ssds?|nvme|hard[ -]?drives?|hdds?|flash[ -]?drives?)\b")),
    ("accessories", re.compile(r"\b(accessories|peripherals?|gadgets?)\b")),
)


def category_search_copy(category) -> CategorySearchCopy | None:
    label = clean_text(getattr(category, "name", "")).lower()
    slug = str(getattr(category, "slug", "") or "").lower().replace("-", " ")
    # Prefer category name. Slug fallback covers titles such as "PC essentials"
    # backed by well named slugs, without forcing every generic category.
    for source in (label, slug):
        for key, pattern in _KEYWORDS:
            if pattern.search(source):
                return CATEGORY_SEARCH_COPY[key]
    return None


def category_metadata(category) -> CategorySearchCopy:
    """Overrides in staff admin take precedence over conservative defaults."""
    preset = category_search_copy(category)
    subject = clean_text(category.name)
    if preset:
        title, description, heading = preset.title, preset.description, preset.heading
    else:
        title = f"{subject} in Uganda | Leosoft UG"
        description = (
            f"Explore {subject.lower()} at Leosoft UG. Compare published products, "
            "prices and details, and contact the team to confirm availability."
        )
        heading = f"{subject} in Uganda"

    return CategorySearchCopy(
        title=clean_text(getattr(category, "seo_title", "")) or title,
        description=clean_text(getattr(category, "seo_description", "")) or description,
        heading=clean_text(getattr(category, "seo_heading", "")) or heading,
    )
