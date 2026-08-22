"""Small, deterministic rules for handling incoming customer enquiries."""

from __future__ import annotations


REQUEST_PRIORITIES = {
    "quote": "high",
    "repair": "high",
    "installation": "high",
    "support": "high",
    "product": "normal",
    "other": "normal",
}


def classify_enquiry(request_type: str | None) -> tuple[str, str]:
    normalized = str(request_type or "other").strip().lower()
    if normalized not in REQUEST_PRIORITIES:
        normalized = "other"
    return normalized, REQUEST_PRIORITIES[normalized]


def response_minutes(priority: str, normal_target: int = 30) -> int:
    normal = max(5, min(int(normal_target), 1440))
    if priority == "urgent":
        return max(5, normal // 6)
    if priority == "high":
        return max(5, normal // 2)
    if priority == "low":
        return min(1440, normal * 2)
    return normal


def uganda_whatsapp_digits(phone: str | None) -> str:
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        return "256" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        return "256" + digits
    return digits if len(digits) >= 9 else ""
