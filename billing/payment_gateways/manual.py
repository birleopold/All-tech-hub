"""Manual/sandbox payment gateway adapter.

Production-safe default: customer-submitted references remain pending for staff
verification. In local development, or when ALLTECH_AUTO_CAPTURE_MANUAL_PAYMENTS
is enabled, submitted references are captured immediately so the full payment
flow can be tested end-to-end without live gateway credentials.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from billing.payment_gateways.base import BasePaymentGateway, PaymentGatewayResult


class ManualPaymentGateway(BasePaymentGateway):
    code = "manual"
    label = "Manual / sandbox payment"

    @property
    def auto_capture_enabled(self) -> bool:
        return bool(
            getattr(
                settings,
                "ALLTECH_AUTO_CAPTURE_MANUAL_PAYMENTS",
                getattr(settings, "DEBUG", False),
            )
        )

    def submit_reference(
        self,
        *,
        document_number: str,
        amount: Decimal,
        method: str,
        reference: str,
        payer_name: str = "",
        payer_email: str = "",
        payer_phone: str = "",
    ) -> PaymentGatewayResult:
        clean_reference = (reference or "").strip()
        if not clean_reference:
            return PaymentGatewayResult(
                status="failed",
                message="Enter the transaction reference so payment can be verified.",
            )
        if amount <= 0:
            return PaymentGatewayResult(
                status="failed",
                message="Payment amount must be greater than zero.",
                provider_reference=clean_reference,
            )
        if self.auto_capture_enabled:
            return PaymentGatewayResult(
                status="captured",
                message="Sandbox payment captured and recorded.",
                provider_reference=clean_reference,
            )
        return PaymentGatewayResult(
            status="pending_verification",
            message="Payment reference submitted for staff verification.",
            provider_reference=clean_reference,
        )
