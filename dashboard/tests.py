from django.contrib.auth.models import User
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

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

    def test_staff_page_labels_are_readable(self):
        self.assertEqual(
            staff_page_label("staff_payment_reconciliation"),
            "Payment reconciliation",
        )
        self.assertEqual(staff_page_label("staff_custom_tool"), "Custom Tool")
        self.assertEqual(staff_page_label(None), "Workspace")
