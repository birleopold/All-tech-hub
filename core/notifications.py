"""Staff in-app notifications and optional email for support tickets."""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from core.models import StaffNotification, SupportTicket

User = get_user_model()


def _prefs_for(user):
    from core.models import StaffNotificationPreference

    if user is None:
        return None
    try:
        return user.notification_preference
    except StaffNotificationPreference.DoesNotExist:
        return None


def staff_notify(user, message: str, link: str = "") -> StaffNotification | None:
    if user is None or not getattr(user, "is_staff", False):
        return None
    prefs = _prefs_for(user)
    if prefs and not prefs.inapp_enabled:
        return None
    # Prevent a rapidly retried background job from flooding the inbox
    # with the same unread event. A later event or a read event remains visible.
    dest = link or reverse("staff_notifications")
    recent_duplicate = StaffNotification.objects.filter(
        recipient=user,
        message=message[:500],
        is_read=False,
        link__endswith="?next=" + quote(dest, safe="/:?=&"),
        created_at__gte=timezone.now() - timezone.timedelta(seconds=90),
    ).order_by("-created_at").first()
    if recent_duplicate:
        return recent_duplicate
    n = StaffNotification.objects.create(
        recipient=user, message=message[:500], link=""
    )
    n.link = (
        reverse("staff_notification_go", kwargs={"pk": n.pk})
        + "?next="
        + quote(dest, safe="/:?=&")
    )
    n.save(update_fields=["link"])
    return n


def _should_email(user, channel: str) -> bool:
    """channel = 'assignment' | 'status'."""
    prefs = _prefs_for(user)
    if prefs is None:
        return True
    if prefs.in_quiet_hours():
        return False
    if channel == "assignment":
        return prefs.email_on_assignment
    if channel == "status":
        return prefs.email_on_status_change
    return True


def notify_ticket_changes(ticket: SupportTicket, old: SupportTicket | None) -> None:
    """Email + in-app alerts when assignment or status changes."""
    if old is None:
        staff_notify(
            ticket.assigned_to,
            f"New support ticket {ticket.reference}: {ticket.subject}",
            reverse("staff_ticket_detail", kwargs={"pk": ticket.pk}),
        )
        return

    if ticket.assigned_to_id != old.assigned_to_id and ticket.assigned_to:
        link = reverse("staff_ticket_detail", kwargs={"pk": ticket.pk})
        staff_notify(
            ticket.assigned_to,
            f"Ticket {ticket.reference} assigned to you",
            link,
        )
        if ticket.assigned_to.email and _should_email(ticket.assigned_to, "assignment"):
            send_mail(
                f"[ALLTECH] Ticket assigned: {ticket.reference}",
                f"You were assigned ticket “{ticket.subject}”.",
                settings.DEFAULT_FROM_EMAIL,
                [ticket.assigned_to.email],
                fail_silently=True,
            )

    if ticket.status != old.status and ticket.customer.email:
        send_mail(
            f"[ALLTECH] Ticket update: {ticket.reference}",
            f"Your request “{ticket.subject}” is now: {ticket.get_status_display()}.",
            settings.DEFAULT_FROM_EMAIL,
            [ticket.customer.email],
            fail_silently=True,
        )


def notify_customer_ticket_comment(ticket: SupportTicket, comment) -> None:
    """Email the customer when a staff member posts a public reply."""
    if comment.is_internal or not ticket.customer.email:
        return
    snippet = (comment.body or "").strip()
    if len(snippet) > 400:
        snippet = snippet[:397] + "…"
    send_mail(
        f"[ALLTECH] Update on ticket {ticket.reference}",
        (
            f"There is a new update on your ticket “{ticket.subject}”.\n\n"
            f"{snippet}\n\n"
            "Sign in to your portal to reply or view the full thread."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [ticket.customer.email],
        fail_silently=True,
    )


def notify_staff_ticket_reply(ticket: SupportTicket, comment) -> None:
    """In-app notification (+ optional email) when the customer posts a reply."""
    target = ticket.assigned_to
    if target is None:
        return
    staff_notify(
        target,
        f"Customer reply on {ticket.reference}",
        reverse("staff_ticket_detail", kwargs={"pk": ticket.pk}),
    )
    if target.email and _should_email(target, "assignment"):
        send_mail(
            f"[ALLTECH] Customer reply: {ticket.reference}",
            f"Customer replied on “{ticket.subject}”. Open the ticket to respond.",
            settings.DEFAULT_FROM_EMAIL,
            [target.email],
            fail_silently=True,
        )
