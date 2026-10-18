from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class FinancialReconciliationTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="reconcile-auditor", password="test-only", is_staff=True
        )
        self.url = reverse("staff_financial_reconciliation")

    def test_requires_finance_permission(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_authorized_staff_can_compare_without_mutation(self):
        self.staff.user_permissions.add(
            Permission.objects.get(codename="view_document_margin")
        )
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"days": "30"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Orders and documents, side by side")
        self.assertEqual(response.context["online_orders"], 0)
        self.assertEqual(response.context["document_count"], 0)
        self.assertEqual(response.context["cost_missing_lines"], 0)
        self.assertEqual(response.context["large_value_documents"], 0)

    def test_non_staff_user_cannot_see_financial_report(self):
        visitor = get_user_model().objects.create_user(
            username="reconcile-visitor", password="test-only"
        )
        visitor.user_permissions.add(
            Permission.objects.get(codename="view_document_margin")
        )
        self.client.force_login(visitor)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
