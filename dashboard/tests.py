from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from automation.models import AutomationJob
from billing.models import CommercialDocument, PaymentSubmission

from dashboard.templatetags.dashboard_ui import staff_page_label


class DashboardAccessTests(TestCase):
    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_view_dashboard(self):
        user = User.objects.create_user("dashboard", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_staff_dashboard_renders_shared_workspace_interface(self):
        user = User.objects.create_user("workspace", password="pw", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("staff_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, static("css/staff_workspace.css"))
        self.assertContains(response, static("css/staff_workspace_refinements.css"))
        self.assertContains(response, 'class="staff-app"')
        self.assertContains(response, "Sales &amp; billing")
        self.assertContains(response, "Recent activity feed")
        self.assertContains(response, "Service schedule")
        self.assertContains(response, "No upcoming service appointments.")

    def test_dashboard_highlights_payment_and_automation_attention(self):
        user = User.objects.create_user(
            "operations-dashboard", password="pw", is_staff=True
        )
        invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-DASHBOARD-ATTENTION",
            customer_name="Dashboard customer",
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("50000.00"),
            due_date=timezone.localdate() - timedelta(days=2),
        )
        PaymentSubmission.objects.create(
            document=invoice,
            amount=Decimal("25000.00"),
            method="mobile_money",
            reference="DASHBOARD-MOMO-1",
        )
        AutomationJob.objects.create(
            idempotency_key="dashboard-failed-job",
            job_type=AutomationJob.TYPE_STOCK_ALERT_EMAIL,
            status=AutomationJob.STATUS_FAILED,
            scheduled_for=timezone.now(),
            next_attempt_at=timezone.now(),
        )
        self.client.force_login(user)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_payment_count"], 1)
        self.assertEqual(response.context["overdue_invoice_count"], 1)
        self.assertEqual(response.context["failed_automation_count"], 1)
        self.assertContains(response, "payment awaiting verification")
        self.assertContains(response, "overdue invoice")
        self.assertContains(response, "failed automation job")

    def test_action_center_shows_finance_items_to_finance_role(self):
        from django.contrib.auth.models import Group
        user = User.objects.create_user("finance-dashboard", is_staff=True)
        user.groups.add(Group.objects.get_or_create(name="Finance")[0])
        invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-DASHBOARD-ROLE",
            customer_name="Example",
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("100.00"),
            due_date=timezone.localdate() - timedelta(days=1),
        )
        PaymentSubmission.objects.create(
            document=invoice, amount=Decimal("50.00"),
            method="mobile_money", reference="DASHBOARD-ROLE-1",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)
        labels = [item["label"] for item in response.context["action_center"]]
        self.assertIn("overdue invoice", labels)
        self.assertIn("payment awaiting verification", labels)
        self.assertNotIn("failed automation job", labels)
        self.assertContains(response, "My Work")
        self.assertContains(response, "Order value")

    def test_technician_action_center_excludes_finance_items(self):
        from django.contrib.auth.models import Group
        user = User.objects.create_user("technician-dashboard", is_staff=True)
        user.groups.add(Group.objects.get_or_create(name="Technician")[0])
        self.client.force_login(user)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_sales_insights"])
        self.assertNotContains(response, "Order value")
        self.assertNotContains(response, "Business health")

    def test_staff_page_labels_are_readable(self):
        self.assertEqual(
            staff_page_label("staff_payment_reconciliation"),
            "Payment reconciliation",
        )
        self.assertEqual(staff_page_label("staff_custom_tool"), "Custom Tool")
        self.assertEqual(staff_page_label(None), "Workspace")
