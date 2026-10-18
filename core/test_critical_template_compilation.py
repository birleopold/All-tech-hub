"""Keep core commerce, job and portal templates compilable before release.

These templates have historically broken due to unmatched {% if %} tags and
missing {% load static %} in included partials.
"""
from django.template.loader import get_template
from django.test import SimpleTestCase


class CriticalTemplateCompilationTests(SimpleTestCase):
    def test_critical_public_and_staff_templates_compile(self):
        templates = (
            "core/home.html",
            "catalog/_marketplace_product_card.html",
            "operations/_offline_field_notes.html",
            "operations/job_detail.html",
            "operations/job_bench.html",
            "billing/document_detail.html",
            "billing/quote_customer.html",
            "billing/revision_comparison.html",
            "portal/documents.html",
        )
        for template in templates:
            with self.subTest(template=template):
                self.assertIsNotNone(get_template(template))
