"""Payment gateway adapters for customer checkout flows."""

from billing.payment_gateways.manual import ManualPaymentGateway

__all__ = ["ManualPaymentGateway"]
