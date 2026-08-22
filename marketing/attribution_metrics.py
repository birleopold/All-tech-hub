"""Dependency-free arithmetic for transparent campaign attribution reporting."""

from __future__ import annotations

from decimal import Decimal


def percentage(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(
        Decimal("0.01")
    )


def merge_channel_metrics(click_rows, lead_rows, order_rows) -> list[dict]:
    """Combine period-matched channel observations without inventing conversion data."""
    channels = {}

    def row_for(source, medium):
        key = (str(source or "direct"), str(medium or "unclassified"))
        if key not in channels:
            channels[key] = {
                "source": key[0],
                "medium": key[1],
                "clicks": 0,
                "leads": 0,
                "orders": 0,
                "revenue": Decimal("0.00"),
            }
        return channels[key]

    for row in click_rows:
        row_for(row["source"], row["medium"])["clicks"] += int(row["clicks"])
    for row in lead_rows:
        row_for(row["source"], row["medium"])["leads"] += int(row["leads"])
    for row in order_rows:
        result = row_for(row["source"], row["medium"])
        result["orders"] += int(row["orders"])
        result["revenue"] += Decimal(str(row["revenue"] or "0"))

    for row in channels.values():
        row["click_to_lead_rate"] = percentage(row["leads"], row["clicks"])
        row["click_to_order_rate"] = percentage(row["orders"], row["clicks"])
        row["average_order_value"] = (
            (row["revenue"] / row["orders"]).quantize(Decimal("0.01"))
            if row["orders"]
            else Decimal("0.00")
        )
    return sorted(
        channels.values(),
        key=lambda row: (-row["revenue"], -row["orders"], -row["clicks"], row["source"]),
    )
