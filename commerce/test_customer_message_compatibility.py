from django.core import mail
from django.test import TestCase, override_settings

from commerce.customer_messages import _deliver
from messaging.models import OutboundEmail


class CustomerMessageCompatibilityTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="orders@example.com",
    )
    def test_existing_callers_without_explicit_key_remain_retry_safe(self):
        row = _deliver(
            to_email="buyer@example.com",
            subject="Review your order ORD-COMPAT-001",
            body="Thank you for your order.",
        )

        self.assertIsNotNone(row)
        self.assertTrue(row.idempotency_key.startswith("legacy-transactional:"))
        self.assertEqual(row.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)

        repeated = _deliver(
            to_email="buyer@example.com",
            subject="Review your order ORD-COMPAT-001",
            body="Thank you for your order.",
        )
        self.assertEqual(repeated.pk, row.pk)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_legacy_non_worker_call_remains_fail_safe_with_console_backend(self):
        self.assertIsNone(
            _deliver(
                to_email="buyer@example.com",
                subject="Review your order ORD-COMPAT-002",
                body="Thank you for your order.",
            )
        )
