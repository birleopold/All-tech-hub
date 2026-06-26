"""Small gateway abstraction for public payment links.

The first adapter is intentionally conservative: it can accept customer
references and either mark them as pending verification or auto-capture them
when explicitly enabled for local/sandbox testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentGatewayResult:
    status: str
    message: str
    provider_reference: str = ""
    checkout_url: str = ""

    @property
    def captured(self) -> bool:
        return self.status == "captured"

    @property
    def pending(self) -> bool:
        return self.status == "pending_verification"


class PaymentGatewayError(Exception):
    """Raised when a gateway cannot create or verify a payment."""


class BasePaymentGateway:
    code = "base"
    label = "Base gateway"

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
        raise NotImplementedError
