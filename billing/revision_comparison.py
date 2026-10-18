"""Read-only, customer-safe comparisons of immutable commercial revisions.

Snapshots can contain internal costs, supplier references and contact details.
Render only explicitly selected buyer-facing fields; never serialize the
whole stored JSON to a template.
"""
from __future__ import annotations

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from billing.models import CommercialDocument, DocumentRevision


def _safe_version(snapshot):
    """Buyer-facing quotation summary; omit internal margin and vendor facts."""
    if not isinstance(snapshot, dict):
        return {}
    lines = snapshot.get("lines")
    if not isinstance(lines, list):
        lines = []
    result = {
        "number": str(snapshot.get("number") or "")[:32],
        "status": str(snapshot.get("status") or "")[:20],
        "issue_date": str(snapshot.get("issue_date") or "")[:40],
        "due_date": str(snapshot.get("due_date") or "")[:40],
        "total": str(snapshot.get("total") or "0")[:30],
        "subtotal": str(snapshot.get("subtotal") or "0")[:30],
        "discount_amount": str(snapshot.get("discount_amount") or "0")[:30],
        "tax_amount": str(snapshot.get("tax_amount") or "0")[:30],
        "shipping_amount": str(snapshot.get("shipping_amount") or "0")[:30],
        "terms": str(snapshot.get("terms") or "")[:5000],
        "lines": [
            {
                "description": str(line.get("description") or "")[:300],
                "quantity": str(line.get("quantity") or "")[:30],
                "unit_price": str(line.get("unit_price") or "")[:30],
                "total": str(line.get("total") or "")[:30],
            }
            for line in lines[:150] if isinstance(line, dict)
        ],
    }
    response = snapshot.get("quote_acceptance")
    if isinstance(response, dict):
        accepted = response.get("customer_accepted")
        result["customer_response"] = (
            "Accepted" if accepted is True else
            "Declined" if accepted is False else "Awaiting response"
        )
    return result


def _context(document, revision, *, staff):
    # snapshotted predecessor vs the latest live version
    predecessor = _safe_version(revision.snapshot)
    current = _safe_version(document.snapshot_data())
    return {
        "document": document,
        "revision": revision,
        "previous_version": predecessor,
        "current_version": current,
        "is_staff_revision": staff,
        "has_differences": (
            predecessor.get("lines") != current.get("lines")
            or predecessor.get("total") != current.get("total")
            or predecessor.get("terms") != current.get("terms")
        ),
    }


@require_GET
def staff_document_revision_compare(request, pk: int, revision_number: int):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404
    if not request.user.has_perm("billing.view_commercialdocument"):
        raise Http404
    document = get_object_or_404(
        CommercialDocument.objects.prefetch_related("lines"), pk=pk
    )
    revision = get_object_or_404(
        DocumentRevision, document=document, revision_number=revision_number
    )
    response = render(
        request, "billing/revision_comparison.html",
        _context(document, revision, staff=True),
    )
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def customer_quote_revision_compare(request, pk: int, revision_number: int):
    from portal.views import _customer_for_request

    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    document = get_object_or_404(
        CommercialDocument.objects.prefetch_related("lines"),
        pk=pk, customer=customer, doc_type=CommercialDocument.TYPE_QUOTE,
    )
    if (
        document.status != CommercialDocument.STATUS_ISSUED
        or not document.is_locked
        or (document.quote_requires_internal_approval and not document.quote_internally_approved)
    ):
        raise Http404
    revision = get_object_or_404(
        DocumentRevision, document=document, revision_number=revision_number
    )
    if revision.snapshot.get("status") not in {
        CommercialDocument.STATUS_ISSUED,
        CommercialDocument.STATUS_EXPIRED,
    }:
        raise Http404
    response = render(
        request, "billing/revision_comparison.html",
        _context(document, revision, staff=False),
    )
    response["Cache-Control"] = "private, no-store"
    return response
