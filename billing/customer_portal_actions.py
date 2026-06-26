from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from billing.models import CommercialDocument, CustomerCredit, DocumentPayment
from billing.payment_gateways import ManualPaymentGateway
from billing.pdf import pdf_response
from core.audit import log_audit_event
from core.models import CompanySettings, ContactMessage


def _money_from_post(value: str, fallback: Decimal) -> Decimal:
    raw = (value or "").strip()
    if not raw:
        return fallback
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError("Enter a valid payment amount.")


def _public_document(token):
    return get_object_or_404(
        CommercialDocument.objects.select_related("customer").prefetch_related(
            "lines__product",
            "lines__product_variant",
            "payments__recorded_by",
        ),
        Q(quote_customer_token=token) | Q(payment_request_token=token),
    )


def _record_online_payment(document: CommercialDocument, amount: Decimal, method: str, reference: str, payer_name: str) -> Decimal:
    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    if method not in dict(DocumentPayment.METHOD_CHOICES):
        method = DocumentPayment.METHOD_MOBILE_MONEY
    with transaction.atomic():
        doc = CommercialDocument.objects.select_for_update().get(pk=document.pk)
        if doc.status == CommercialDocument.STATUS_CANCELLED:
            raise ValidationError("Cancelled documents cannot receive payments.")
        if not doc.supports_payment_request:
            raise ValidationError("Payments are available for invoices and proformas only.")
        if doc.balance_due <= 0:
            raise ValidationError("This document is already fully paid.")
        applied = min(amount, doc.balance_due).quantize(Decimal("0.01"))
        excess = max(Decimal("0"), amount - applied).quantize(Decimal("0.01"))
        DocumentPayment.objects.create(
            document=doc,
            amount=applied,
            method=method,
            reference=reference[:120],
            note=(f"Customer payment link: {payer_name}" if payer_name else "Customer payment link")[:255],
            recorded_by=None,
        )
        doc.amount_paid = (doc.amount_paid + applied).quantize(Decimal("0.01"))
        if doc.status == CommercialDocument.STATUS_DRAFT:
            doc.status = CommercialDocument.STATUS_ISSUED
        doc.sync_payment_status()
        doc.save(update_fields=["amount_paid", "status", "updated_at"])
        if excess > 0 and doc.customer_id:
            CustomerCredit.objects.create(
                customer=doc.customer,
                customer_name=doc.display_customer_name,
                amount=excess,
                remaining_amount=excess,
                source_document=doc,
                reference=reference[:120],
                note="Customer payment exceeded document balance.",
                created_by=None,
            )
        log_audit_event(
            actor=None,
            verb="billing.payment_link_recorded",
            summary=f"{doc.number}: online payment {applied}; credit {excess}",
            target=doc,
        )
        return applied


def _save_payment_confirmation(document: CommercialDocument, amount: Decimal, method: str, reference: str, payer_name: str, payer_email: str, payer_phone: str) -> None:
    ContactMessage.objects.create(
        name=(payer_name or document.display_customer_name)[:120],
        email=(payer_email or document.display_customer_email or "payments@invalid.local")[:254],
        phone=(payer_phone or document.display_customer_phone)[:64],
        subject=f"Payment confirmation for {document.number}",
        message=(
            f"Customer submitted payment confirmation for {document.number}.\n\n"
            f"Method: {dict(DocumentPayment.METHOD_CHOICES).get(method, method or 'Not specified')}\n"
            f"Amount: {amount}\n"
            f"Reference: {reference}\n"
            f"Customer: {payer_name or document.display_customer_name}\n"
            f"Email: {payer_email or document.display_customer_email}\n"
            f"Phone: {payer_phone or document.display_customer_phone}"
        ),
    )
    log_audit_event(
        actor=None,
        verb="billing.payment_confirmation_submitted",
        summary=f"Payment confirmation submitted for {document.number}: {reference[:80]}",
        target=document,
    )


def _quote_post(request, document: CommercialDocument, token):
    if document.quote_customer_accepted is not None:
        messages.info(request, "This quotation already has a customer response.")
        return redirect("quote_customer_portal", token=token)
    action = request.POST.get("action")
    signature_name = (request.POST.get("signature_name") or "").strip()
    if action == "accept" and signature_name:
        document.quote_customer_accepted = True
        document.quote_customer_signature_name = signature_name[:200]
        document.quote_customer_responded_at = timezone.now()
        document.save(
            update_fields=[
                "quote_customer_accepted",
                "quote_customer_signature_name",
                "quote_customer_responded_at",
                "updated_at",
            ]
        )
        log_audit_event(
            actor=request.user if request.user.is_authenticated else None,
            verb="billing.quote_customer_accepted",
            summary=f"Quote {document.number} accepted by {signature_name}",
            target=document,
        )
        messages.success(request, "Thank you — quotation accepted.")
    elif action == "decline":
        document.quote_customer_accepted = False
        document.quote_customer_decline_reason = (request.POST.get("decline_reason") or "").strip()[:500]
        document.quote_customer_responded_at = timezone.now()
        document.save(
            update_fields=[
                "quote_customer_accepted",
                "quote_customer_decline_reason",
                "quote_customer_responded_at",
                "updated_at",
            ]
        )
        log_audit_event(
            actor=request.user if request.user.is_authenticated else None,
            verb="billing.quote_customer_declined",
            summary=f"Quote {document.number} declined",
            target=document,
        )
        messages.info(request, "Quotation declined. Our team will follow up.")
    else:
        messages.error(request, "Enter your full name to accept, or use Decline.")
    return redirect("quote_customer_portal", token=token)


def _payment_post(request, document: CommercialDocument, token):
    payer_name = (request.POST.get("payer_name") or "").strip()
    payer_email = (request.POST.get("payer_email") or "").strip()
    payer_phone = (request.POST.get("payer_phone") or "").strip()
    method = (request.POST.get("method") or DocumentPayment.METHOD_MOBILE_MONEY).strip()
    reference = (request.POST.get("reference") or "").strip()
    try:
        amount = _money_from_post(request.POST.get("amount") or "", document.balance_due)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("payment_request_portal", token=token)
    gateway = ManualPaymentGateway()
    result = gateway.submit_reference(
        document_number=document.number,
        amount=amount,
        method=method,
        reference=reference,
        payer_name=payer_name,
        payer_email=payer_email,
        payer_phone=payer_phone,
    )
    if result.captured:
        try:
            applied = _record_online_payment(document, amount, method, result.provider_reference, payer_name)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, f"Payment of {applied} recorded successfully.")
    elif result.pending:
        _save_payment_confirmation(document, amount, method, result.provider_reference, payer_name, payer_email, payer_phone)
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)
    return redirect("payment_request_portal", token=token)


def _render_center(request, document: CommercialDocument, token, mode: str):
    gateway = ManualPaymentGateway()
    return render(
        request,
        "billing/customer_action_center.html",
        {
            "document": document,
            "company": CompanySettings.load(),
            "public_token": token,
            "mode": mode,
            "payment_methods": list(DocumentPayment.METHOD_CHOICES),
            "gateway": gateway,
            "can_pay": document.supports_payment_request
            and document.status != CommercialDocument.STATUS_CANCELLED
            and document.balance_due > 0,
        },
    )


def customer_quote_action_center(request, token):
    document = get_object_or_404(
        CommercialDocument.objects.select_related("customer").prefetch_related("lines", "payments"),
        quote_customer_token=token,
        doc_type=CommercialDocument.TYPE_QUOTE,
    )
    if request.method == "POST":
        return _quote_post(request, document, token)
    return _render_center(request, document, token, "quote")


def customer_payment_action_center(request, token):
    document = get_object_or_404(
        CommercialDocument.objects.select_related("customer").prefetch_related("lines", "payments"),
        payment_request_token=token,
    )
    if not document.supports_payment_request:
        raise Http404
    if request.method == "POST":
        return _payment_post(request, document, token)
    return _render_center(request, document, token, "payment")


def customer_document_pdf(request, token):
    document = _public_document(token)
    return pdf_response(
        document,
        inline=request.GET.get("download") != "1",
        copy=request.GET.get("copy") == "1",
    )
