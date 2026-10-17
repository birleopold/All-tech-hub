import tempfile
from datetime import time
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import CommercialDocument, DocumentPayment, allocate_document_number
from catalog.models import Category, Product
from core.barcodes import normalize_code39
from core.filters import apply_job_filters, apply_ticket_filters
from core.models import (
    BusinessHours,
    CompanySettings,
    StaffNotification,
    StaffSavedSearch,
    StaffTwoFactor,
    SupportTicket,
    TicketComment,
    hours_summary,
    is_open_now,
)
from core.totp import generate_secret, token_for, verify_token
from crm.models import Customer
from operations.models import JobCard


class BarcodeTests(TestCase):
    def test_code39_normalizes_scanner_safe_text(self):
        self.assertEqual(normalize_code39("sku_abc/12"), "SKU-ABC/12")


@override_settings(ENFORCE_STAFF_ROLES=True)
class StaffRoleAuthorizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "limited-staff", password="pw", is_staff=True
        )
        self.client.force_login(self.user)

    def test_staff_without_inventory_permission_is_denied(self):
        response = self.client.get(reverse("staff_inventory"))
        self.assertEqual(response.status_code, 403)

    def test_staff_with_inventory_permission_is_allowed(self):
        permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="view_stockadjustment",
        )
        self.user.user_permissions.add(permission)
        response = self.client.get(reverse("staff_inventory"))
        self.assertEqual(response.status_code, 200)

    def test_staff_without_audit_permission_cannot_view_security_diagnostics(self):
        response = self.client.get(reverse("staff_security_diagnostics"))
        self.assertEqual(response.status_code, 403)

    def test_staff_with_audit_permission_can_view_security_diagnostics(self):
        permission = Permission.objects.get(
            content_type__app_label="core",
            codename="view_auditevent",
        )
        self.user.user_permissions.add(permission)
        response = self.client.get(reverse("staff_security_diagnostics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security diagnostics")


class TwoFactorTests(TestCase):
    def test_totp_round_trip(self):
        secret = generate_secret()
        token = token_for(secret, timestamp=1_700_000_000)
        self.assertTrue(verify_token(secret, token, timestamp=1_700_000_000))

    def test_staff_login_requires_code_when_enabled(self):
        user = User.objects.create_user(
            "twofactor", password="secret", is_staff=True
        )
        secret = generate_secret()
        StaffTwoFactor.objects.create(user=user, secret=secret, enabled=True)
        bad = self.client.post(
            reverse("login"),
            {"username": "twofactor", "password": "secret", "otp": "000000"},
        )
        self.assertEqual(bad.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        good = self.client.post(
            reverse("login"),
            {
                "username": "twofactor",
                "password": "secret",
                "otp": token_for(secret),
            },
        )
        self.assertEqual(good.status_code, 302)


class CompanyCurrencyTests(TestCase):
    def test_singleton_loads_ugx(self):
        company = CompanySettings.load()
        self.assertEqual(company.currency_code, "UGX")


class PlatformMaturityTests(TestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_service_worker_is_root_scoped_javascript(self):
        response = self.client.get(reverse("service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("application/javascript", response["Content-Type"])
        self.assertContains(response, "CACHE_NAME")

    def test_offline_page_renders(self):
        response = self.client.get(reverse("offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You are currently offline")

    def test_security_headers_are_sent_in_report_only_mode(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertIn("camera=()", response["Permissions-Policy"])
        self.assertIn("default-src 'self'", response["Content-Security-Policy-Report-Only"])
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(SECURITY_HEADERS_ENABLED=False)
    def test_security_headers_can_be_disabled(self):
        response = self.client.get(reverse("home"))
        self.assertNotIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn("Permissions-Policy", response)

    def test_security_diagnostics_renders_backup_freshness(self):
        user = User.objects.create_user(
            "diagnostics", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(user)
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            backup_dir = base_dir / "backups"
            backup_dir.mkdir()
            (backup_dir / "alltech-db-test.sqlite3").write_text("db", encoding="utf-8")
            with override_settings(BASE_DIR=base_dir):
                response = self.client.get(reverse("staff_security_diagnostics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup freshness")
        # Unverified raw SQLite dumps are intentionally not advertised
        # as verified recovery points in the security diagnostics.
        self.assertNotContains(response, "alltech-db-test.sqlite3")


class OperationsMonitorCommandTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            "ops-manager", password="pw", is_staff=True, is_superuser=True
        )
        self.customer = Customer.objects.create(name="Monitor", email="monitor@example.com")
        self.category = Category.objects.create(name="Monitor", slug="monitor")

    def test_monitor_creates_and_deduplicates_notifications(self):
        from datetime import timedelta

        Product.objects.create(
            category=self.category,
            name="Low cable",
            slug="low-cable-monitor",
            price=Decimal("10.00"),
            stock_quantity=1,
            reorder_level=5,
        )
        job = JobCard.objects.create(
            customer=self.customer,
            title="Overdue repair",
            priority=JobCard.PRIORITY_URGENT,
            assigned_to=self.manager,
        )
        JobCard.objects.filter(pk=job.pk).update(
            received_on=timezone.now() - timedelta(hours=24)
        )
        doc = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number=allocate_document_number("INV"),
            customer=self.customer,
            status=CommercialDocument.STATUS_ISSUED,
            issue_date=timezone.localdate() - timedelta(days=10),
            due_date=timezone.localdate() - timedelta(days=1),
            total=Decimal("100.00"),
        )
        DocumentPayment.objects.create(
            document=doc,
            amount=Decimal("25.00"),
            method=DocumentPayment.METHOD_CASH,
            recorded_by=self.manager,
        )

        call_command("monitor_operations")
        first_count = StaffNotification.objects.filter(recipient=self.manager).count()
        self.assertGreaterEqual(first_count, 3)

        call_command("monitor_operations")
        second_count = StaffNotification.objects.filter(recipient=self.manager).count()
        self.assertEqual(second_count, first_count)


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
