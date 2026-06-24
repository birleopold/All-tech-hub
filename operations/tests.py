from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent, StaffNotification, SupportTicket
from crm.models import Customer
from operations.job_status import allowed_next_statuses, validate_job_status_transition
from operations.models import JobCard, JobFeedback, JobStatusEvent


class JobStatusFsmTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Pat", email="pat@example.com")

    def test_intake_to_diagnosing_allowed(self):
        job = JobCard.objects.create(
            customer=self.customer,
            title="Screen",
            status=JobCard.STATUS_INTAKE,
        )
        job.status = JobCard.STATUS_DIAGNOSING
        job.full_clean()

    def test_intake_to_completed_rejected(self):
        job = JobCard.objects.create(
            customer=self.customer,
            title="Screen",
            status=JobCard.STATUS_INTAKE,
        )
        job.status = JobCard.STATUS_COMPLETED
        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_terminal_completed_has_no_exits(self):
        self.assertEqual(len(allowed_next_statuses(JobCard.STATUS_COMPLETED)), 0)

    def test_validate_helper_noop_same_status(self):
        validate_job_status_transition(previous=JobCard.STATUS_INTAKE, new=JobCard.STATUS_INTAKE)


class JobStatusAuditTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Pat", email="pat2@example.com")
        self.user = User.objects.create_user("tech", "tech@example.com", "pw", is_staff=True)

    def test_form_save_logs_status_change(self):
        job = JobCard.objects.create(
            customer=self.customer,
            title="Battery",
            status=JobCard.STATUS_INTAKE,
        )
        from operations.forms import JobCardForm

        form = JobCardForm(
            {
                "customer": self.customer.pk,
                "title": "Battery",
                "description": "",
                "device_type": "",
                "device_make": "",
                "device_model": "",
                "serial_number": "",
                "accessories_received": "",
                "problem_reported": "",
                "diagnosis": "",
                "resolution": "",
                "status": JobCard.STATUS_DIAGNOSING,
                "priority": JobCard.PRIORITY_NORMAL,
                "assigned_to": "",
                "labor_hours": "0",
                "estimated_completion": "",
                "scheduled_for": "",
                "scheduled_until": "",
                "related_order": "",
                "related_invoice": "",
            },
            instance=job,
        )
        form._audit_user = self.user
        self.assertTrue(form.is_valid(), form.errors)
        before = AuditEvent.objects.count()
        form.save()
        self.assertEqual(AuditEvent.objects.count(), before + 1)
        ev = AuditEvent.objects.order_by("-id").first()
        self.assertEqual(ev.verb, "job.status_change")
        self.assertEqual(ev.actor_id, self.user.pk)


class JobDaysInStatusTests(TestCase):
    def test_days_non_negative(self):
        customer = Customer.objects.create(name="A", email="a@example.com")
        job = JobCard.objects.create(
            customer=customer,
            title="T",
            status=JobCard.STATUS_INTAKE,
        )
        self.assertGreaterEqual(job.days_in_current_status, 0)


class JobLabelViewTests(TestCase):
    def test_job_label_sheet_renders_job_number(self):
        customer = Customer.objects.create(name="Label Customer", email="label@example.com")
        user = User.objects.create_user("job-label", "job-label@example.com", "pw", is_staff=True)
        job = JobCard.objects.create(
            customer=customer,
            title="Printer repair",
            serial_number="PR-123",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("staff_job_labels", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, job.number)
        self.assertContains(response, "PR-123")


class JobScheduleOverlapTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Sched", email="sched@example.com")
        self.tech = User.objects.create_user("tech2", "tech2@example.com", "pw", is_staff=True)
        self.start = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)

    def test_overlapping_assignment_rejected(self):
        JobCard.objects.create(
            customer=self.customer,
            title="First",
            assigned_to=self.tech,
            scheduled_for=self.start,
            scheduled_until=self.start + timedelta(hours=1),
        )
        second = JobCard(
            customer=self.customer,
            title="Second",
            assigned_to=self.tech,
            scheduled_for=self.start + timedelta(minutes=30),
            scheduled_until=self.start + timedelta(hours=2),
        )
        with self.assertRaises(ValidationError):
            second.full_clean()


class SupportTicketTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Cust", email="cust@example.com")
        self.staff = User.objects.create_user("agent", "agent@example.com", "pw", is_staff=True)

    def test_ticket_gets_reference(self):
        t = SupportTicket.objects.create(
            customer=self.customer,
            subject="VPN",
            description="Cannot connect",
        )
        self.assertTrue(t.reference.startswith("TK-"))

    def test_assignment_creates_notification(self):
        t = SupportTicket.objects.create(
            customer=self.customer,
            subject="Email",
            description="Broken",
            assigned_to=self.staff,
        )
        self.assertTrue(
            StaffNotification.objects.filter(
                recipient=self.staff, message__icontains=t.reference
            ).exists()
        )

    def test_portal_ticket_list_requires_login(self):
        client = Client()
        r = client.get(reverse("portal_tickets"))
        self.assertEqual(r.status_code, 302)


class JobStatusEventTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="EvCust", email="ev@example.com")

    def test_event_created_on_status_change(self):
        job = JobCard.objects.create(
            customer=self.customer,
            title="Event",
            status=JobCard.STATUS_INTAKE,
        )
        self.assertEqual(JobStatusEvent.objects.filter(job=job).count(), 1)
        job.status = JobCard.STATUS_DIAGNOSING
        job.save()
        events = JobStatusEvent.objects.filter(job=job).order_by("id")
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.last().from_status, JobCard.STATUS_INTAKE)
        self.assertEqual(events.last().to_status, JobCard.STATUS_DIAGNOSING)


class JobFeedbackTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Feedback", email="fb@example.com")
        self.user = User.objects.create_user("fbuser", "fbuser@example.com", "pw")
        self.customer.user = self.user
        self.customer.save()

    def _completed_job(self):
        job = JobCard.objects.create(
            customer=self.customer, title="Done", status=JobCard.STATUS_INTAKE
        )
        for nxt in [
            JobCard.STATUS_DIAGNOSING,
            JobCard.STATUS_IN_REPAIR,
            JobCard.STATUS_QA,
            JobCard.STATUS_READY,
            JobCard.STATUS_COMPLETED,
        ]:
            job.status = nxt
            job.save()
        return job

    def test_feedback_form_submits(self):
        job = self._completed_job()
        client = Client()
        client.force_login(self.user)
        url = reverse("portal_job_feedback", kwargs={"pk": job.pk})
        resp = client.post(url, {"rating": 5, "comment": "Great work"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(JobFeedback.objects.filter(job=job, rating=5).exists())

    def test_feedback_rejects_invalid_rating(self):
        job = self._completed_job()
        client = Client()
        client.force_login(self.user)
        url = reverse("portal_job_feedback", kwargs={"pk": job.pk})
        resp = client.post(url, {"rating": 9, "comment": ""}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(JobFeedback.objects.filter(job=job).exists())


class JobCalendarTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("calstaff", "cal@example.com", "pw", is_staff=True)
        self.customer = Customer.objects.create(name="CalCust", email="cal-cust@example.com")

    def test_calendar_requires_staff(self):
        client = Client()
        r = client.get(reverse("staff_job_calendar"))
        self.assertEqual(r.status_code, 302)

    def test_calendar_renders_for_staff(self):
        from django.utils import timezone

        when = timezone.now() + timedelta(days=1)
        JobCard.objects.create(
            customer=self.customer,
            title="Sched",
            assigned_to=self.staff,
            scheduled_for=when.replace(minute=0, second=0, microsecond=0),
        )
        client = Client()
        client.force_login(self.staff)
        r = client.get(reverse("staff_job_calendar"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sched")
