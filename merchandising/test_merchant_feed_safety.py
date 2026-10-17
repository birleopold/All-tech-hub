"""Merchant-approved exports never fail open on a database outage."""
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(MERCHANT_STRICT_READINESS=True)
class MerchantApprovalOutageTests(TestCase):
    @patch("merchandising.merchant.ProductCommerceProfile.objects.filter")
    def test_approval_lookup_error_returns_retryable_503(self, mocked_filter):
        mocked_filter.side_effect = OperationalError("readiness unavailable")
        response = self.client.get(reverse("google_merchant_feed"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Retry-After"], "300")
        self.assertEqual(response["X-Merchant-Readiness"], "schema-unavailable")
        self.assertNotIn(b"<item>", response.content)
