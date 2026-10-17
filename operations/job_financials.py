"""Clear, non-duplicating job-to-invoice financial reconciliation.

Only one-to-one links are eligible for comparison. This intentionally does not
subtract job expenses from invoice gross profit: invoiced part costs may
already include expenses recorded here. No allocation should be invented.
"""
from decimal import Decimal

from billing.financials import (
    document_business_cost, document_owner_payout,
    document_recognized_income,
)
from billing.models import CommercialDocument
from operations.models import JobCard, JobExpense


def job_financial_reconciliation(job: JobCard) -> dict:
    expenses = JobExpense.objects.filter(job_id=job.pk)
    recorded = sum(
        expenses.values_list("amount", flat=True), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    result = {
        "recorded_direct_cost": recorded,
        "invoice": None,
        "invoice_income": None,
        "invoice_business_cost": None,
        "invoice_partner_due": None,
        "invoice_contribution": None,
        "status": "No linked invoice",
        "note": (
            "Only receipt-backed job costs are shown. Add the customer invoice "
            "to compare its recognised income; this is not a net job profit."
        ),
    }
    document = job.related_invoice
    if document is None:
        return result
    result["invoice"] = document
    if document.customer_id and document.customer_id != job.customer_id:
        result["status"] = "Customer mismatch"
        result["note"] = "The linked invoice belongs to another customer. Review this link."
        return result
    if document.doc_type != CommercialDocument.TYPE_INVOICE:
        result["status"] = "Not an invoice"
        result["note"] = "Link an invoice before comparing financial values."
        return result
    if JobCard.objects.filter(related_invoice_id=document.pk).exclude(
        pk=job.pk
    ).exists():
        result["status"] = "Shared invoice"
        result["note"] = (
            "This invoice is shared by multiple jobs. Its totals cannot be "
            "allocated to any individual job without explicit allocation."
        )
        return result
    if document.status not in (
        CommercialDocument.STATUS_ISSUED,
        CommercialDocument.STATUS_PARTIALLY_PAID,
        CommercialDocument.STATUS_PAID,
    ):
        result["status"] = "Invoice not issued"
        result["note"] = "The invoice is not issued/recognised yet."
        return result
    income = document_recognized_income(document)
    cost = document_business_cost(document)
    result.update({
        "invoice_income": income,
        "invoice_business_cost": cost,
        "invoice_partner_due": document_owner_payout(document),
        "invoice_contribution": (income - cost).quantize(Decimal("0.01")),
        "status": "Comparison available",
        "note": (
            "Invoice contribution reflects invoiced line costs only. Job "
            "expenses are reported separately because costs can overlap. "
            "Do not add or subtract these amounts as a certified job profit."
        ),
    })
    return result
