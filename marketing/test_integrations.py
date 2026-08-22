import unittest

from marketing.integrations import integration_capabilities


class IntegrationCapabilitiesTests(unittest.TestCase):
    def test_unconfigured_integrations_are_not_reported_as_connected(self):
        rows = integration_capabilities()
        self.assertTrue(all(not row["ready"] for row in rows))

    def test_whatsapp_is_described_as_manual(self):
        rows = integration_capabilities(whatsapp_available=True)
        whatsapp = next(row for row in rows if row["name"].startswith("WhatsApp"))
        self.assertTrue(whatsapp["ready"])
        self.assertIn("Staff-assisted", whatsapp["state"])

    def test_gateway_never_claims_unsupported_live_processing(self):
        rows = integration_capabilities(facebook_connected=True, instagram_connected=True, email_connected=True)
        gateway = next(row for row in rows if row["name"] == "Online payment gateway")
        self.assertFalse(gateway["ready"])


if __name__ == "__main__":
    unittest.main()
