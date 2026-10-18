"""Regression checks for consent-aware Google acquisition instrumentation."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class GoogleGrowthTrackingTests(SimpleTestCase):
    def test_contact_events_never_send_contact_details(self):
        script = (Path(settings.BASE_DIR) / "static/js/marketing_analytics.js").read_text(encoding="utf-8")
        self.assertIn('name: "contact_click"', script)
        self.assertIn("contact_channel: channel", script)
        self.assertIn("page_path: window.location.pathname", script)
        self.assertIn("if (contactLink && integrationsLoaded", script)
        self.assertIn('if (internalPath) return;', script)
        self.assertIn("const requireConsent =", script)
        self.assertNotIn("contact_number:", script)
        self.assertNotIn("contact_message:", script)

    def test_google_growth_actions_are_accessible_from_existing_staff_seo(self):
        template = (Path(settings.BASE_DIR) / "templates/dashboard/seo_control_center.html").read_text(encoding="utf-8")
        for expected in ("google-growth-workflow", "staff_catalogue_bulk_enrichment",
                         "https://merchants.google.com/", "https://analytics.google.com/",
                         "https://search.google.com/search-console", "https://business.google.com/"):
            self.assertIn(expected, template)
