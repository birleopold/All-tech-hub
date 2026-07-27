ROOT_COMMERCIAL_SLUGS = (
    "laptop-prices-in-uganda",
    "dell-laptops-uganda",
    "hp-laptops-uganda",
    "lenovo-laptops-uganda",
    "macbook-prices-in-uganda",
    "refurbished-laptops-uganda",
    "business-laptops-uganda",
    "student-laptops-uganda",
    "gaming-laptops-uganda",
    "workstation-laptops-uganda",
    "core-i5-laptops-uganda",
    "core-i7-laptops-uganda",
    "touchscreen-laptops-uganda",
    "desktop-computer-prices-in-uganda",
    "printer-prices-in-uganda",
    "wifi-router-prices-in-uganda",
    "cctv-camera-prices-in-uganda",
    "ssd-prices-in-uganda",
    "external-hard-drive-prices-in-uganda",
    "computer-accessories-uganda",
    "monitor-prices-in-uganda",
    "ups-prices-in-uganda",
)

ROOT_COMMERCIAL_SLUG_SET = frozenset(ROOT_COMMERCIAL_SLUGS)


def commercial_page_path(slug: str) -> str:
    if slug in ROOT_COMMERCIAL_SLUG_SET:
        return f"/{slug}/"
    return f"/commercial/{slug}/"
