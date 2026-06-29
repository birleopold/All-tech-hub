from decimal import Decimal

from billing.models import CommercialDocument, CommercialLine

COMMISSION_SOURCE_TYPES = (
    CommercialLine.SOURCE_EXTERNAL,
    CommercialLine.SOURCE_CONSIGNMENT,
)
RECOGNIZED_STATUSES = (
    CommercialDocument.STATUS_ISSUED,
    CommercialDocument.STATUS_PARTIALLY_PAID,
    CommercialDocument.STATUS_PAID,
)


def is_commission_line(line: CommercialLine) -> bool:
    return line.source_type in COMMISSION_SOURCE_TYPES


def document_net_sales(document: CommercialDocument) -> Decimal:
    return (document.subtotal - document.discount_amount).quantize(Decimal("0.01"))


def document_discount_ratio(document: CommercialDocument) -> Decimal:
    if document.subtotal <= 0:
        return Decimal("1")
    return (document_net_sales(document) / document.subtotal).quantize(Decimal("0.000001"))


def line_net_after_document_discount(line: CommercialLine) -> Decimal:
    return (line.net_subtotal * document_discount_ratio(line.document)).quantize(Decimal("0.01"))


def line_owner_payout(line: CommercialLine) -> Decimal:
    if not is_commission_line(line):
        return Decimal("0.00")
    return line.total_cost


def line_business_cost(line: CommercialLine) -> Decimal:
    if is_commission_line(line):
        return Decimal("0.00")
    return line.total_cost


def line_recognized_income(line: CommercialLine) -> Decimal:
    net = line_net_after_document_discount(line)
    if is_commission_line(line):
        return (net - line_owner_payout(line)).quantize(Decimal("0.01"))
    return net


def line_profit(line: CommercialLine) -> Decimal:
    return (line_recognized_income(line) - line_business_cost(line)).quantize(Decimal("0.01"))


def line_margin_percent(line: CommercialLine) -> Decimal:
    income = line_recognized_income(line)
    if income <= 0:
        return Decimal("0.00")
    return (line_profit(line) / income * Decimal("100")).quantize(Decimal("0.01"))


def document_customer_total(document: CommercialDocument) -> Decimal:
    return document.total.quantize(Decimal("0.01"))


def document_owner_payout(document: CommercialDocument) -> Decimal:
    return sum((line_owner_payout(line) for line in document.lines.all()), Decimal("0.00")).quantize(Decimal("0.01"))


def document_business_cost(document: CommercialDocument) -> Decimal:
    return sum((line_business_cost(line) for line in document.lines.all()), Decimal("0.00")).quantize(Decimal("0.01"))


def document_recognized_income(document: CommercialDocument) -> Decimal:
    return sum((line_recognized_income(line) for line in document.lines.all()), Decimal("0.00")).quantize(Decimal("0.01"))


def document_profit(document: CommercialDocument) -> Decimal:
    return (document_recognized_income(document) - document_business_cost(document)).quantize(Decimal("0.01"))


def document_margin_percent(document: CommercialDocument) -> Decimal:
    income = document_recognized_income(document)
    if income <= 0:
        return Decimal("0.00")
    return (document_profit(document) / income * Decimal("100")).quantize(Decimal("0.01"))


def queryset_financial_summary(documents) -> dict:
    recognized_income = Decimal("0.00")
    customer_total = Decimal("0.00")
    owner_payout = Decimal("0.00")
    business_cost = Decimal("0.00")

    for document in documents:
        customer_total += document_customer_total(document)
        recognized_income += document_recognized_income(document)
        owner_payout += document_owner_payout(document)
        business_cost += document_business_cost(document)

    profit = recognized_income - business_cost
    margin = Decimal("0.00")
    if recognized_income > 0:
        margin = (profit / recognized_income * Decimal("100")).quantize(Decimal("0.01"))

    return {
        "customer_total": customer_total.quantize(Decimal("0.01")),
        "revenue": recognized_income.quantize(Decimal("0.01")),
        "recognized_income": recognized_income.quantize(Decimal("0.01")),
        "owner_payout": owner_payout.quantize(Decimal("0.01")),
        "cost": business_cost.quantize(Decimal("0.01")),
        "business_cost": business_cost.quantize(Decimal("0.01")),
        "profit": profit.quantize(Decimal("0.01")),
        "margin": margin,
    }
