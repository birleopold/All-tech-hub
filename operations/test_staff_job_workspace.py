from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.models import Customer
from operations.models import JobCard


class StaffJobWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("job-staff", password="pw", is_staff=True)
        cls.customer = Customer.objects.create(
            name="Service Customer",
            email="service@example.com",
        )
        cls.urgent_job = JobCard.objects.create(
            number="JC-WORKSPACE-1",
            customer=cls.customer,
            title="Urgent laptop repair",
            device_make="Lenovo",
            device_model="ThinkPad",
            priority=JobCard.PRIORITY_URGENT,
            assigned_to=cls.user,
            scheduled_for=timezone.now() + timedelta(days=1),
        )
        cls.normal_job = JobCard.objects.create(
            number="JC-WORKSPACE-2",
            customer=cls.customer,
            title="Desktop diagnostics",
            device_type="Desktop",
            priority=JobCard.PRIORITY_NORMAL,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_job_workspace_renders_queue_metrics(self):
        response = self.client.get(reverse("staff_jobs"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["job_stats"]["total"], 2)
        self.assertEqual(response.context["job_stats"]["open"], 2)
        self.assertEqual(response.context["job_stats"]["scheduled"], 1)
        self.assertEqual(response.context["job_stats"]["urgent"], 1)
        self.assertContains(response, "Service operations")
        self.assertContains(response, "Service queue")
        self.assertContains(response, "staff-priority-pill--danger")

    def test_job_workspace_filters_by_priority_and_search(self):
        priority_response = self.client.get(
            reverse("staff_jobs"), {"priority": JobCard.PRIORITY_URGENT}
        )
        search_response = self.client.get(reverse("staff_jobs"), {"q": "Desktop"})

        self.assertEqual(priority_response.context["paginator"].count, 1)
        self.assertContains(priority_response, "JC-WORKSPACE-1")
        self.assertNotContains(priority_response, "JC-WORKSPACE-2")
        self.assertEqual(search_response.context["paginator"].count, 1)
        self.assertContains(search_response, "JC-WORKSPACE-2")
