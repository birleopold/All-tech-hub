from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.forms import CustomerForm
from crm.models import Customer


class CustomerWorkspaceTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="customer-staff", password="staff-password", is_staff=True
        )
        self.customer = Customer.objects.create(
            name="Kampala Buyer", email="buyer@example.com", phone="0700123456"
        )

    def test_customer_directory_supports_search(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_customers"), {"q": "0700123456"})
        self.assertContains(response, "Kampala Buyer")

    def test_customer_detail_combines_customer_history(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("staff_customer_detail", args=[self.customer.pk])
        )
        self.assertContains(response, "Lifetime order value")

    def test_duplicate_email_is_rejected_case_insensitively(self):
        form = CustomerForm(
            data={"name": "Another buyer", "email": "BUYER@example.com"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
