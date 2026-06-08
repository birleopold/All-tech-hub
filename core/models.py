from datetime import datetime, time

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class CompanySettings(models.Model):
    """Singleton-style company profile used on documents and the public site."""

    company_name = models.CharField(max_length=200, default="ALLTECH")
    legal_name = models.CharField(max_length=200, blank=True)
    tagline = models.CharField(max_length=300, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    website = models.URLField(blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=120, blank=True)
    tax_id = models.CharField(max_length=64, blank=True, verbose_name="Tax / VAT ID")
    bank_details = models.TextField(blank=True, help_text="Shown on invoices / proformas.")
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text="Percentage, e.g. 15.00"
    )
    currency_code = models.CharField(max_length=8, default="UGX")
    logo = models.ImageField(upload_to="company/", blank=True, null=True)
    sla_low_hours = models.PositiveIntegerField(
        default=168, help_text="SLA target (hours) for Low priority work — default 1 week."
    )
    sla_normal_hours = models.PositiveIntegerField(
        default=72, help_text="SLA target (hours) for Normal priority — default 3 days."
    )
    sla_high_hours = models.PositiveIntegerField(
        default=24, help_text="SLA target (hours) for High priority — default 24h."
    )
    sla_urgent_hours = models.PositiveIntegerField(
        default=8, help_text="SLA target (hours) for Urgent priority — default 8h."
    )

    class Meta:
        verbose_name = "Company settings"
        verbose_name_plural = "Company settings"

    def __str__(self) -> str:
        return self.company_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "CompanySettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def sla_hours_for(self, priority: str) -> int:
        return {
            "low": self.sla_low_hours,
            "normal": self.sla_normal_hours,
            "high": self.sla_high_hours,
            "urgent": self.sla_urgent_hours,
        }.get(priority, self.sla_normal_hours)


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=64, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.subject} — {self.email}"


class Announcement(models.Model):
    """Short-lived notices shown on the portal home page and optionally site-wide."""

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    active_from = models.DateField(
        null=True,
        blank=True,
        help_text="Show on or after this date. Leave blank to show immediately.",
    )
    active_until = models.DateField(
        null=True,
        blank=True,
        help_text="Hide after this date. Leave blank for no end date.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]

    def __str__(self) -> str:
        return self.title


class KnowledgeArticle(models.Model):
    """Public help articles (customer portal knowledge base)."""

    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.title)[:200] or "article"
            slug = base
            n = 2
            while KnowledgeArticle.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


def _due_in_label(due_at, is_open: bool) -> str:
    if due_at is None:
        return ""
    now = timezone.now()
    delta = due_at - now
    secs = int(delta.total_seconds())
    if not is_open:
        return ""
    if secs < 0:
        secs = -secs
        unit, val = _humanise_seconds(secs)
        return f"Overdue {val}{unit}"
    unit, val = _humanise_seconds(secs)
    return f"Due in {val}{unit}"


def _humanise_seconds(seconds: int) -> tuple[str, int]:
    if seconds < 60:
        return ("s", seconds)
    minutes = seconds // 60
    if minutes < 60:
        return ("m", minutes)
    hours = minutes // 60
    if hours < 48:
        return ("h", hours)
    days = hours // 24
    return ("d", days)


class SupportTicket(models.Model):
    """Customer support request (portal or staff); patterns from VIMBA customer-helpdesk."""

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CLOSED, "Closed"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    CATEGORY_GENERAL = "general"
    CATEGORY_BILLING = "billing"
    CATEGORY_RMA = "rma"
    CATEGORY_WARRANTY = "warranty"
    CATEGORY_CHOICES = [
        (CATEGORY_GENERAL, "General"),
        (CATEGORY_BILLING, "Billing"),
        (CATEGORY_RMA, "Return / RMA"),
        (CATEGORY_WARRANTY, "Warranty claim"),
    ]

    reference = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.PROTECT, related_name="support_tickets"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets_created",
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN
    )
    priority = models.CharField(
        max_length=16, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GENERAL,
        help_text="General support, billing query, RMA / return, or warranty claim.",
    )
    related_order = models.ForeignKey(
        "commerce.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    related_serial = models.ForeignKey(
        "catalog.ProductSerial",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.reference or 'TK'} — {self.subject}"

    @property
    def is_open(self) -> bool:
        return self.status not in (self.STATUS_RESOLVED, self.STATUS_CLOSED)

    @property
    def sla_due_at(self):
        from datetime import timedelta

        if not self.created_at:
            return None
        hours = CompanySettings.load().sla_hours_for(self.priority)
        return self.created_at + timedelta(hours=hours)

    @property
    def is_overdue(self) -> bool:
        due = self.sla_due_at
        if due is None or not self.is_open:
            return False
        return timezone.now() > due

    @property
    def due_in_label(self) -> str:
        return _due_in_label(self.sla_due_at, self.is_open)

    def save(self, *args, **kwargs) -> None:
        from billing.models import allocate_document_number

        old = None
        if self.pk:
            old = SupportTicket.objects.filter(pk=self.pk).first()
        if not self.reference:
            self.reference = allocate_document_number("TK")
        super().save(*args, **kwargs)
        from core.notifications import notify_ticket_changes

        notify_ticket_changes(self, old)


class StaffSavedSearch(models.Model):
    """Named filter presets for staff list views (jobs, tickets, etc.)."""

    SCOPE_JOBS = "jobs"
    SCOPE_TICKETS = "tickets"
    SCOPE_CHOICES = [
        (SCOPE_JOBS, "Job cards"),
        (SCOPE_TICKETS, "Support tickets"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_saved_searches",
    )
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES)
    name = models.CharField(max_length=100)
    params = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scope", "name"],
                name="unique_staff_saved_search_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_scope_display()})"


class StaffNotification(models.Model):
    """In-app staff inbox (lightweight port of VIMBA notification-service idea)."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_notifications",
    )
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.message[:60]


class BusinessHours(models.Model):
    """Weekday opening hours; one row per day (0=Mon … 6=Sun)."""

    DAYS = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    weekday = models.PositiveSmallIntegerField(choices=DAYS, unique=True)
    is_open = models.BooleanField(default=True)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["weekday"]
        verbose_name = "Business hours"
        verbose_name_plural = "Business hours"

    def __str__(self) -> str:
        return self.get_weekday_display()

    @property
    def display_hours(self) -> str:
        if not self.is_open or not self.open_time or not self.close_time:
            return "Closed"
        return f"{self.open_time.strftime('%H:%M')}–{self.close_time.strftime('%H:%M')}"


def is_open_now() -> bool:
    """True if the current local weekday/time is within configured hours."""
    now = timezone.localtime()
    row = BusinessHours.objects.filter(weekday=now.weekday()).first()
    if not row or not row.is_open or not row.open_time or not row.close_time:
        return False
    cur = now.time().replace(microsecond=0)
    return row.open_time <= cur <= row.close_time


def hours_summary():
    """Cached-friendly list of hours rows (creates missing days as closed)."""
    existing = {h.weekday: h for h in BusinessHours.objects.all()}
    rows = []
    for wd, label in BusinessHours.DAYS:
        rows.append(
            existing.get(wd)
            or BusinessHours(weekday=wd, is_open=False, note="")
        )
    return rows


class TicketComment(models.Model):
    """Threaded conversation on a SupportTicket (helpdesk pattern)."""

    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_comments",
    )
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal-only note hidden from the customer portal.",
    )
    attachment = models.FileField(
        upload_to="tickets/%Y/%m/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Comment on {self.ticket.reference}"


class StaffNotificationPreference(models.Model):
    """Per-staff toggles for in-app + email channels."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_on_assignment = models.BooleanField(default=True)
    email_on_status_change = models.BooleanField(default=False)
    inapp_enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Prefs — {self.user.get_username()}"

    def in_quiet_hours(self, when=None) -> bool:
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        now = (when or timezone.localtime()).time()
        start, end = self.quiet_hours_start, self.quiet_hours_end
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end


class AuditEvent(models.Model):
    """Append-only staff audit trail (Phase 7 MVP)."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    verb = models.CharField(max_length=64, db_index=True)
    summary = models.CharField(max_length=500)
    target_type = models.CharField(
        max_length=80,
        blank=True,
        help_text="Dotted app label and model name, e.g. operations.jobcard",
    )
    target_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.verb}"
