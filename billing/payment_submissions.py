"""Durable, auditable verification of payments made without a provider API."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from billing.models import CommercialDocument, DocumentPayment, PaymentSubmission
from core.audit import log_audit_event
from core.models import CompanySettings
from reliability.models import PaymentAttempt
from reliability.services import create_payment_attempt, transition_payment_attempt


METHOD_ALIASES = {
    "mobile money": DocumentPayment.METHOD_MOBILE_MONEY,
    "mobile_money": DocumentPayment.METHOD_MOBILE_MONEY,
    "bank transfer": DocumentPayment.METHOD_TRANSFER,
    "transfer": DocumentPayment.METHOD_TRANSFER,
    "card": DocumentPayment.METHOD_CARD,
    "cash": DocumentPayment.METHOD_CASH,
    "cash deposit": DocumentPayment.METHOD_CASH,
    "cheque": DocumentPayment.METHOD_CHEQUE,
    "other": DocumentPayment.METHOD_OTHER,
}


@transaction.atomic
def submit_payment_confirmation(
    *, document, amount, method, reference, payer_name="", payer_email="",
    payer_phone="", actor=None
):
    document = CommercialDocument.objects.select_for_update().get(pk=document.pk)
    if not document.supports_payment_request:
        raise ValidationError("Only invoices and proformas accept payment confirmations.")
    if document.status in (
        CommercialDocument.STATUS_CANCELLED, CommercialDocument.STATUS_EXPIRED
    ) or document.balance_due <= 0:
        raise ValidationError("This payment request is no longer active.")
    method = METHOD_ALIASES.get((method or "").strip().lower())
    if not method:
        raise ValidationError("Choose a supported payment method.")
    reference = (reference or "").strip().upper()
    if not reference or len(reference) > 120:
        raise ValidationError("Enter a valid transaction reference.")
    try:
        amount = Decimal(str(amount or document.balance_due)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Enter a valid payment amount.")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError("The payment amount must be greater than zero.")
    if amount > document.balance_due:
        raise ValidationError("The submitted amount cannot exceed the outstanding balance.")

    existing = PaymentSubmission.objects.select_for_update().filter(
        method=method, reference__iexact=reference
    ).first()
    if existing:
        if existing.document_id == document.pk and existing.amount == amount:
            return existing, False
        raise ValidationError("This transaction reference was already submitted.")
    if DocumentPayment.objects.filter(method=method, reference__iexact=reference).exists():
        raise ValidationError("This transaction reference has already been recorded.")

    try:
        with transaction.atomic():
            submission = PaymentSubmission.objects.create(
                document=document,
                amount=amount,
                method=method,
                reference=reference,
                payer_name=(payer_name or document.display_customer_name or "")[:120],
                payer_email=(payer_email or document.display_customer_email or "")[:254],
                payer_phone=(payer_phone or document.display_customer_phone or "")[:64],
            )
    except IntegrityError as exc:
        raise ValidationError("This transaction reference was already submitted.") from exc

    if document.order_id:
        attempt, _ = create_payment_attempt(
            order=document.order,
            idempotency_key=f"document-payment-submission:{submission.pk}",
            amount=amount,
            provider=f"manual_{method}",
            currency=CompanySettings.load().currency_code or "UGX",
            external_reference=reference,
            safe_metadata={
                "document_id": document.pk,
                "document_number": document.number,
                "submission_id": submission.pk,
                "method": method,
            },
            actor=actor,
        )
        if attempt.status == PaymentAttempt.STATUS_CREATED:
            attempt = transition_payment_attempt(
                attempt, PaymentAttempt.STATUS_PENDING, actor=actor
            )
        submission.payment_attempt = attempt
        submission.save(update_fields=["payment_attempt", "updated_at"])

    log_audit_event(
        actor=actor,
        verb="billing.payment_confirmation_submitted",
        summary=f"Payment confirmation submitted for {document.number}: {reference}",
        target=submission,
    )
    return submission, True


@transaction.atomic
def verify_payment_submission(submission, *, actor):
    submission = PaymentSubmission.objects.select_for_update().select_related(
        "document", "payment_attempt"
    ).get(pk=submission.pk)
    if submission.status != PaymentSubmission.STATUS_PENDING:
        raise ValidationError("This payment submission has already been reviewed.")
    document = CommercialDocument.objects.select_for_update().get(
        pk=submission.document_id
    )
    if document.status in (
        CommercialDocument.STATUS_CANCELLED, CommercialDocument.STATUS_EXPIRED
    ):
        raise ValidationError("Payments cannot be applied to an inactive document.")
    if submission.amount > document.balance_due:
        raise ValidationError("This payment exceeds the remaining document balance.")
    if DocumentPayment.objects.filter(
        method=submission.method, reference__iexact=submission.reference
    ).exists():
        raise ValidationError("This transaction reference has already been recorded.")

    now = timezone.now()
    if submission.payment_attempt_id:
        transition_payment_attempt(
            submission.payment_attempt,
            PaymentAttempt.STATUS_PAID,
            actor=actor,
            external_reference=submission.reference,
        )
    payment = DocumentPayment.objects.create(
        document=document,
        amount=submission.amount,
        method=submission.method,
        reference=submission.reference,
        note=f"Verified customer payment submission #{submission.pk}.",
        recorded_by=actor,
        reconciled=True,
        reconciled_at=now,
        reconciled_by=actor,
    )
    document.amount_paid = (document.amount_paid + submission.amount).quantize(
        Decimal("0.01")
    )
    if document.status == CommercialDocument.STATUS_DRAFT:
        document.status = CommercialDocument.STATUS_ISSUED
    document.sync_payment_status()
    document.save(update_fields=["amount_paid", "status", "updated_at"])

    submission.status = PaymentSubmission.STATUS_VERIFIED
    submission.reviewed_by = actor
    submission.reviewed_at = now
    submission.recorded_payment = payment
    submission.save(update_fields=[
        "status", "reviewed_by", "reviewed_at", "recorded_payment", "updated_at"
    ])
    log_audit_event(
        actor=actor,
        verb="billing.payment_confirmation_verified",
        summary=(
            f"Verified payment {submission.reference} for {document.number}: "
            f"{submission.amount}; balance {document.balance_due}"
        ),
        target=submission,
    )
    return payment


@transaction.atomic
def reject_payment_submission(submission, *, actor, reason=""):
    submission = PaymentSubmission.objects.select_for_update().select_related(
        "payment_attempt"
    ).get(pk=submission.pk)
    if submission.status != PaymentSubmission.STATUS_PENDING:
        raise ValidationError("This payment submission has already been reviewed.")
    reason = (reason or "Payment could not be verified.").strip()[:255]
    if submission.payment_attempt_id:
        transition_payment_attempt(
            submission.payment_attempt,
            PaymentAttempt.STATUS_FAILED,
            actor=actor,
            last_error=reason,
        )
    submission.status = PaymentSubmission.STATUS_REJECTED
    submission.review_note = reason
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=[
        "status", "review_note", "reviewed_by", "reviewed_at", "updated_at"
    ])
    log_audit_event(
        actor=actor,
        verb="billing.payment_confirmation_rejected",
        summary=f"Rejected payment {submission.reference}: {reason}",
        target=submission,
    )
    return submission
