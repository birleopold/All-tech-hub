"""Consent-aware customer care tasks derived from real customer activity."""

from datetime import datetime, time, timedelta
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import ProductSerial
from commerce.models import Order
from core.audit import log_audit_event
from core.models import CompanySettings
from core.notifications import staff_notify
from crm.models import Customer
from loyalty.models import CustomerMarketingPreference
from messaging.models import OutboundEmail
from messaging.utils import send_outbound_email
from reports.models import CustomerFollowUp


OPEN_STATUSES = [
    CustomerFollowUp.STATUS_PENDING,
    CustomerFollowUp.STATUS_IN_PROGRESS,
]


def _sales_owners():
    users = list(
        get_user_model().objects.filter(
            is_active=True, is_staff=True, groups__name__in=["Sales", "Manager"]
        ).distinct().order_by("pk")[:20]
    )
    if users:
        return users
    return list(
        get_user_model().objects.filter(
            is_active=True, is_staff=True, is_superuser=True
        ).order_by("pk")[:10]
    )


def _due_datetime(day):
    return timezone.make_aware(
        datetime.combine(day, time(hour=9)),
        timezone.get_current_timezone(),
    )


def _assign_and_notify(task, owners, index):
    if not owners:
        return
    task.assigned_to = owners[index % len(owners)]
    task.save(update_fields=["assigned_to", "updated_at"])
    staff_notify(
        task.assigned_to,
        f"Customer follow-up: {task.customer.name} · {task.get_follow_up_type_display()}",
        reverse("staff_retention_dashboard"),
    )


def refresh_retention_followups(*, limit=50, dry_run=False):
    limit = max(1, min(int(limit or 50), 200))
    today = timezone.localdate()
    now = timezone.now()
    warranty_horizon = today + timedelta(days=30)
    dormant_cutoff = now - timedelta(days=90)
    owners = [] if dry_run else _sales_owners()
    created_warranty = created_dormant = existing = 0

    serials = ProductSerial.objects.filter(
        status=ProductSerial.STATUS_SOLD,
        sold_to__isnull=False,
        sold_at__isnull=False,
        warranty_months__gt=0,
    ).select_related("product", "sold_to").order_by("sold_at", "pk")
    for serial in serials.iterator(chunk_size=100):
        if created_warranty >= limit:
            break
        expires = serial.warranty_expires_on
        if not expires or expires < today or expires > warranty_horizon:
            continue
        key = f"warranty-expiry:{serial.pk}:{expires.isoformat()}"
        if CustomerFollowUp.objects.filter(idempotency_key=key).exists():
            existing += 1
            continue
        if dry_run:
            created_warranty += 1
            continue
        days_left = (expires - today).days
        task, was_created = CustomerFollowUp.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "follow_up_type": CustomerFollowUp.TYPE_WARRANTY_EXPIRY,
                "customer": serial.sold_to,
                "product_serial": serial,
                "priority": (
                    CustomerFollowUp.PRIORITY_URGENT
                    if days_left <= 7
                    else CustomerFollowUp.PRIORITY_HIGH
                ),
                "due_at": _due_datetime(max(today, expires - timedelta(days=7))),
                "note": (
                    f"{serial.product.name} (serial {serial.serial_number}) "
                    f"warranty expires on {expires.isoformat()}."
                )[:500],
            },
        )
        if was_created:
            _assign_and_notify(task, owners, created_warranty + created_dormant)
            created_warranty += 1
        else:
            existing += 1

    dormant = Customer.objects.annotate(
        last_order_at=Max(
            "orders__placed_at",
            filter=~Q(orders__status=Order.STATUS_CANCELLED),
        )
    ).filter(last_order_at__lt=dormant_cutoff).order_by("last_order_at", "pk")[:limit]
    for customer in dormant:
        latest_order = Order.objects.filter(customer=customer).exclude(
            status=Order.STATUS_CANCELLED
        ).order_by("-placed_at", "-pk").first()
        if latest_order is None:
            continue
        key = f"dormant-customer:{customer.pk}:{latest_order.placed_at.date().isoformat()}"
        if CustomerFollowUp.objects.filter(idempotency_key=key).exists():
            existing += 1
            continue
        if dry_run:
            created_dormant += 1
            continue
        task, was_created = CustomerFollowUp.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "follow_up_type": CustomerFollowUp.TYPE_DORMANT_CUSTOMER,
                "customer": customer,
                "order": latest_order,
                "priority": CustomerFollowUp.PRIORITY_NORMAL,
                "due_at": now,
                "note": (
                    f"No completed purchase since "
                    f"{latest_order.placed_at.date().isoformat()}. "
                    "Check communication consent before promotional outreach."
                )[:500],
            },
        )
        if was_created:
            _assign_and_notify(task, owners, created_warranty + created_dormant)
            created_dormant += 1
        else:
            existing += 1

    return {
        "warranty_created": created_warranty,
        "dormant_created": created_dormant,
        "existing": existing,
        "dry_run": bool(dry_run),
    }


def customer_outreach_allowed(task, channel):
    if task.follow_up_type == CustomerFollowUp.TYPE_WARRANTY_EXPIRY:
        return True
    preference = CustomerMarketingPreference.objects.filter(
        customer_id=task.customer_id,
        withdrawn_at__isnull=True,
    ).first()
    if preference is None:
        return False
    channel_allowed = (
        preference.whatsapp_marketing
        if channel == "whatsapp"
        else preference.email_marketing
    )
    return bool(
        channel_allowed
        and (preference.product_updates or preference.special_offers)
    )


def followup_message(task):
    company = CompanySettings.load()
    if task.follow_up_type == CustomerFollowUp.TYPE_WARRANTY_EXPIRY:
        serial = task.product_serial
        if serial is None:
            raise ValidationError("The product warranty is no longer available.")
        return (
            f"Hello {task.customer.name}, your warranty for {serial.product.name} "
            f"(serial {serial.serial_number}) expires on "
            f"{serial.warranty_expires_on}. Contact {company.company_name} "
            "if you need a device inspection, repair, or warranty assistance."
        )
    return (
        f"Hello {task.customer.name}, we hope your previous purchase is serving "
        f"you well. The {company.company_name} team is available if you need "
        "computer support, accessories, repairs, or advice."
    )


@transaction.atomic
def send_followup_email(task, *, actor):
    task = CustomerFollowUp.objects.select_for_update().select_related(
        "customer", "product_serial", "product_serial__product"
    ).get(pk=task.pk)
    if not task.is_open:
        raise ValidationError("This customer follow-up is already closed.")
    if not task.customer.email:
        raise ValidationError("The customer does not have an email address.")
    if not customer_outreach_allowed(task, "email"):
        raise ValidationError(
            "This customer has not consented to marketing email. Use a service "
            "call or record an offline follow-up instead."
        )
    transactional = task.follow_up_type == CustomerFollowUp.TYPE_WARRANTY_EXPIRY
    body = followup_message(task)
    if not transactional:
        preference = task.customer.marketing_preference
        company = CompanySettings.load()
        base = (company.website or "https://leosoftug.com").rstrip("/")
        body += (
            "\n\nManage your communication preferences: "
            f"{base}{reverse('marketing_unsubscribe_all', kwargs={'token': preference.unsubscribe_token})}"
        )
    log = send_outbound_email(
        to_email=task.customer.email,
        subject=(
            f"Warranty reminder: {task.product_serial.product.name}"
            if transactional
            else f"A check-in from {CompanySettings.load().company_name}"
        ),
        body=body,
        created_by=actor,
        category=(
            OutboundEmail.CATEGORY_TRANSACTIONAL
            if transactional
            else OutboundEmail.CATEGORY_MARKETING
        ),
        idempotency_key=f"retention-followup-email:{task.pk}",
    )
    if log.status not in {
        OutboundEmail.STATUS_SENT, OutboundEmail.STATUS_DELIVERED
    }:
        raise ValidationError(
            "The customer email could not be delivered. Check the email activity log."
        )
    task.status = CustomerFollowUp.STATUS_IN_PROGRESS
    task.last_contacted_at = timezone.now()
    task.assigned_to = task.assigned_to or actor
    task.save(update_fields=[
        "status", "last_contacted_at", "assigned_to", "updated_at"
    ])
    log_audit_event(
        actor=actor,
        verb="retention.followup_email_sent",
        summary=f"Customer follow-up email sent to {task.customer.name}.",
        target=task,
    )
    return log


@transaction.atomic
def open_followup_whatsapp(task, *, actor):
    task = CustomerFollowUp.objects.select_for_update().select_related(
        "customer", "product_serial", "product_serial__product"
    ).get(pk=task.pk)
    if not task.is_open:
        raise ValidationError("This customer follow-up is already closed.")
    if not customer_outreach_allowed(task, "whatsapp"):
        raise ValidationError(
            "This customer has not consented to WhatsApp marketing. "
            "Use a service call or record an offline follow-up instead."
        )
    digits = "".join(ch for ch in (task.customer.phone or "") if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = f"256{digits[1:]}"
    if len(digits) < 9:
        raise ValidationError("The customer does not have a valid WhatsApp number.")
    task.status = CustomerFollowUp.STATUS_IN_PROGRESS
    task.last_contacted_at = timezone.now()
    task.assigned_to = task.assigned_to or actor
    task.save(update_fields=[
        "status", "last_contacted_at", "assigned_to", "updated_at"
    ])
    log_audit_event(
        actor=actor,
        verb="retention.followup_whatsapp_opened",
        summary=f"Opened customer follow-up WhatsApp chat for {task.customer.name}.",
        target=task,
    )
    return f"https://wa.me/{digits}?text={quote(followup_message(task))}"


@transaction.atomic
def close_followup(task, *, actor, dismissed=False, note=""):
    task = CustomerFollowUp.objects.select_for_update().get(pk=task.pk)
    if not task.is_open:
        raise ValidationError("This customer follow-up is already closed.")
    task.status = (
        CustomerFollowUp.STATUS_DISMISSED
        if dismissed
        else CustomerFollowUp.STATUS_COMPLETED
    )
    task.completed_at = timezone.now()
    task.completed_by = actor
    if note.strip():
        task.note = note.strip()[:500]
    task.save(update_fields=[
        "status", "completed_at", "completed_by", "note", "updated_at"
    ])
    log_audit_event(
        actor=actor,
        verb=(
            "retention.followup_dismissed"
            if dismissed
            else "retention.followup_completed"
        ),
        summary=f"Closed customer follow-up for {task.customer.name}.",
        target=task,
    )
    return task
