from django.contrib.auth.models import User
from django.test import TestCase

from datetime import time

from catalog.models import Category, Product
from core.filters import apply_job_filters, apply_ticket_filters
from core.models import (
    BusinessHours,
    CompanySettings,
    StaffSavedSearch,
    SupportTicket,
    TicketComment,
    hours_summary,
    is_open_now,
)
from crm.models import Customer
from operations.models import JobCard


class CompanyCurrencyTests(TestCase):
    def test_singleton_loads_ugx(self):
        company = CompanySettings.load()
        self.assertEqual(company.currency_code, "UGX")


class ListFilterTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="F", email="f@example.com")
        JobCard.objects.create(customer=self.customer, title="Laptop screen", status=JobCard.STATUS_INTAKE)
        SupportTicket.objects.create(
            customer=self.customer, subject="Help", description="Need support"
        )

    def test_apply_job_filters_by_query(self):
        qs = JobCard.objects.all()
        filtered = apply_job_filters(qs, {"q": "Laptop"})
        self.assertEqual(filtered.count(), 1)

    def test_apply_ticket_filters_by_status(self):
        qs = SupportTicket.objects.all()
        filtered = apply_ticket_filters(qs, {"status": SupportTicket.STATUS_OPEN})
        self.assertEqual(filtered.count(), 1)


class StaffSavedSearchTests(TestCase):
    def test_saved_search_unique_per_user_scope(self):
        user = User.objects.create_user("u1", "u1@example.com", "pw", is_staff=True)
        StaffSavedSearch.objects.create(
            user=user,
            scope=StaffSavedSearch.SCOPE_JOBS,
            name="Urgent",
            params={"priority": "urgent"},
        )
        with self.assertRaises(Exception):
            StaffSavedSearch.objects.create(
                user=user,
                scope=StaffSavedSearch.SCOPE_JOBS,
                name="Urgent",
                params={"priority": "high"},
            )


class LowStockTests(TestCase):
    def test_is_low_stock_when_at_reorder_level(self):
        cat = Category.objects.create(name="C", slug="c-low")
        p = Product.objects.create(
            category=cat,
            name="Cable",
            slug="cable-low",
            price=10,
            stock_quantity=2,
            reorder_level=5,
        )
        self.assertTrue(p.is_low_stock)


class TicketCommentTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("agent", "agent@example.com", "pw", is_staff=True)
        self.customer = Customer.objects.create(name="Pat", email="pat@example.com")
        self.ticket = SupportTicket.objects.create(
            customer=self.customer,
            subject="Slow PC",
            description="Boots in 5 minutes",
        )

    def test_internal_comment_hidden_from_customer_query(self):
        TicketComment.objects.create(ticket=self.ticket, author=self.staff, body="Public reply")
        TicketComment.objects.create(
            ticket=self.ticket, author=self.staff, body="Internal note", is_internal=True
        )
        public = self.ticket.comments.filter(is_internal=False)
        self.assertEqual(public.count(), 1)
        self.assertEqual(public.first().body, "Public reply")


class SlaTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.customer = Customer.objects.create(name="SLA", email="sla@example.com")
        self.ticket = SupportTicket.objects.create(
            customer=self.customer,
            subject="Server down",
            description="Help",
            priority=SupportTicket.PRIORITY_URGENT,
        )
        SupportTicket.objects.filter(pk=self.ticket.pk).update(
            created_at=timezone.now() - timedelta(hours=9)
        )
        self.ticket.refresh_from_db()

    def test_urgent_ticket_is_overdue_after_9h_default_8(self):
        self.assertTrue(self.ticket.is_overdue)

    def test_resolved_ticket_not_overdue(self):
        self.ticket.status = SupportTicket.STATUS_RESOLVED
        self.ticket.save()
        self.assertFalse(self.ticket.is_overdue)

    def test_company_sla_hours_map(self):
        co = CompanySettings.load()
        self.assertEqual(co.sla_hours_for("urgent"), co.sla_urgent_hours)
        self.assertEqual(co.sla_hours_for("nonsense"), co.sla_normal_hours)


class BusinessHoursTests(TestCase):
    def test_hours_summary_returns_seven_rows(self):
        rows = hours_summary()
        self.assertEqual(len(rows), 7)

    def test_is_open_now_handles_no_rows(self):
        self.assertFalse(is_open_now())

    def test_display_hours_when_closed(self):
        row = BusinessHours.objects.create(weekday=6, is_open=False)
        self.assertEqual(row.display_hours, "Closed")

    def test_display_hours_when_open(self):
        row = BusinessHours.objects.create(
            weekday=0, is_open=True, open_time=time(8, 0), close_time=time(17, 30)
        )
        self.assertEqual(row.display_hours, "08:00–17:30")
