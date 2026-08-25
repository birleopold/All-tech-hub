from __future__ import annotations

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from automation.models import AutomationJob
from billing.models import CommercialDocument, DocumentPayment, PaymentSubmission
from catalog.stock_alerts import low_stock_products
from core.models import StaffNotification, SupportTicket
from core.notifications import staff_notify
from operations.models import JobCard


class Command(BaseCommand):
    help = "Create staff notifications for overdue work, payment exceptions, and low stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print notifications that would be created without writing them.",
        )

    def handle(self, *args, **options):
        self.dry_run = bool(options["dry_run"])
        self.today = timezone.localdate()
        self.created = 0
        self.skipped = 0

        self._notify_overdue_jobs()
        self._notify_overdue_tickets()
        self._notify_overdue_invoices()
        self._notify_payment_exceptions()
        self._notify_pending_payment_submissions()
        self._notify_failed_automation()
        self._notify_low_stock()

        self.stdout.write(
            self.style.SUCCESS(
                f"Operational monitor complete: {self.created} notification(s), "
                f"{self.skipped} duplicate(s) skipped."
            )
        )

    def _role_users(self, *roles):
        User = get_user_model()
        users = list(
            User.objects.filter(is_staff=True, groups__name__in=roles)
            .distinct()
            .order_by("username")
        )
        if users:
            return users
        users = list(User.objects.filter(is_staff=True, is_superuser=True).order_by("username"))
        if users:
            return users
        return list(User.objects.filter(is_staff=True).order_by("username")[:5])

    def _notify_once(self, user, message: str, link: str):
        if user is None:
            return
        msg = message[:500]
        if StaffNotification.objects.filter(
            recipient=user,
            message=msg,
            created_at__date=self.today,
        ).exists():
            self.skipped += 1
            return
        if self.dry_run:
            self.stdout.write(f"[dry-run] {user.get_username()}: {msg} -> {link}")
            self.created += 1
            return
        staff_notify(user, msg, link)
        self.created += 1

    def _notify_overdue_jobs(self):
        overdue = [
            job
            for job in JobCard.objects.exclude(
                status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
            ).select_related("assigned_to")
            if job.is_overdue
        ]
        by_user = defaultdict(list)
        fallback = self._role_users("Manager", "Technician")
        for job in overdue:
            targets = [job.assigned_to] if job.assigned_to_id else fallback
            for user in targets:
                by_user[user].append(job)
        for user, jobs in by_user.items():
            refs = ", ".join(job.number for job in jobs[:5])
            more = f" (+{len(jobs) - 5} more)" if len(jobs) > 5 else ""
            self._notify_once(
                user,
                f"{len(jobs)} overdue job(s): {refs}{more}",
                reverse("staff_job_bench"),
            )

    def _notify_overdue_tickets(self):
        overdue = [
            ticket
            for ticket in SupportTicket.objects.exclude(
                status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED]
            ).select_related("assigned_to")
            if ticket.is_overdue
        ]
        by_user = defaultdict(list)
        fallback = self._role_users("Manager", "Sales")
        for ticket in overdue:
            targets = [ticket.assigned_to] if ticket.assigned_to_id else fallback
            for user in targets:
                by_user[user].append(ticket)
        for user, tickets in by_user.items():
            refs = ", ".join(ticket.reference for ticket in tickets[:5])
            more = f" (+{len(tickets) - 5} more)" if len(tickets) > 5 else ""
            self._notify_once(
                user,
                f"{len(tickets)} overdue support ticket(s): {refs}{more}",
                reverse("staff_tickets") + "?due=overdue",
            )

    def _notify_overdue_invoices(self):
        overdue = [
            doc
            for doc in CommercialDocument.objects.filter(
                doc_type=CommercialDocument.TYPE_INVOICE,
                due_date__lt=self.today,
            ).exclude(
                status__in=[
                    CommercialDocument.STATUS_PAID,
                    CommercialDocument.STATUS_CANCELLED,
                ]
            )
            if doc.balance_due > 0
        ]
        if not overdue:
            return
        refs = ", ".join(doc.number for doc in overdue[:5])
        more = f" (+{len(overdue) - 5} more)" if len(overdue) > 5 else ""
        for user in self._role_users("Manager", "Finance"):
            self._notify_once(
                user,
                f"{len(overdue)} overdue invoice(s): {refs}{more}",
                reverse("staff_reports"),
            )

    def _notify_payment_exceptions(self):
        count = DocumentPayment.objects.filter(reconciled=False).count()
        if count <= 0:
            return
        for user in self._role_users("Manager", "Finance"):
            self._notify_once(
                user,
                f"{count} unreconciled payment(s) need review.",
                reverse("staff_payment_reconciliation"),
            )

    def _notify_pending_payment_submissions(self):
        pending = list(
            PaymentSubmission.objects.filter(
                status=PaymentSubmission.STATUS_PENDING
            ).select_related("document").order_by("created_at")[:50]
        )
        if not pending:
            return
        refs = ", ".join(item.reference for item in pending[:5])
        more = f" (+{len(pending) - 5} more)" if len(pending) > 5 else ""
        for user in self._role_users("Manager", "Finance"):
            self._notify_once(
                user,
                f"{len(pending)} customer payment(s) awaiting verification: {refs}{more}",
                reverse("staff_payment_reconciliation"),
            )

    def _notify_failed_automation(self):
        failed = AutomationJob.objects.filter(
            status=AutomationJob.STATUS_FAILED
        ).count()
        if failed <= 0:
            return
        for user in self._role_users("Manager"):
            self._notify_once(
                user,
                f"{failed} automation job(s) failed and need review.",
                reverse("staff_automation_control"),
            )

    def _notify_low_stock(self):
        items = low_stock_products(limit=None)
        if not items:
            return
        names = ", ".join(item.name for item in items[:5])
        more = f" (+{len(items) - 5} more)" if len(items) > 5 else ""
        for user in self._role_users("Manager", "Inventory"):
            self._notify_once(
                user,
                f"{len(items)} low-stock item(s): {names}{more}",
                reverse("staff_products") + "?low=1",
            )
