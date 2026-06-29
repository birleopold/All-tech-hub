from decimal import Decimal

from billing.financials import (
    has_outsourced_service_details,
    line_owner_payout,
    line_profit,
    line_recognized_income,
)
from billing.models import CommercialLine


def partner_name(line: CommercialLine) -> str:
    return (line.supplier_name or "").strip() or "Unspecified partner"


def partner_category(line: CommercialLine) -> str:
    if has_outsourced_service_details(line):
        return "Outsourced service"
    if line.source_type == CommercialLine.SOURCE_CONSIGNMENT:
        return "Consignment"
    if line.source_type == CommercialLine.SOURCE_EXTERNAL:
        return "External purchase"
    return line.get_source_type_display()


def partner_payables_summary(lines) -> list[dict]:
    rows = {}
    for line in lines:
        amount_due = line_owner_payout(line)
        if amount_due <= 0:
            continue
        key = (partner_name(line), partner_category(line))
        row = rows.setdefault(
            key,
            {
                "partner": key[0],
                "category": key[1],
                "line_count": 0,
                "documents": set(),
                "customer_total": Decimal("0.00"),
                "amount_due": Decimal("0.00"),
                "recognized_income": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
        )
        row["line_count"] += 1
        row["documents"].add(line.document.number)
        row["customer_total"] += line.line_total
        row["amount_due"] += amount_due
        row["recognized_income"] += line_recognized_income(line)
        row["profit"] += line_profit(line)

    result = []
    for row in rows.values():
        row["document_count"] = len(row.pop("documents"))
        row["customer_total"] = row["customer_total"].quantize(Decimal("0.01"))
        row["amount_due"] = row["amount_due"].quantize(Decimal("0.01"))
        row["recognized_income"] = row["recognized_income"].quantize(Decimal("0.01"))
        row["profit"] = row["profit"].quantize(Decimal("0.01"))
        result.append(row)
    result.sort(key=lambda item: item["amount_due"], reverse=True)
    return result
