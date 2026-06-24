from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class DashboardAccessTests(TestCase):
    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_view_dashboard(self):
        user = User.objects.create_user("dashboard", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)
