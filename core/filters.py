"""Shared list-filter helpers (ported from VIMBA customer-helpdesk)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.models import CompanySettings, SupportTicket
from operations.models import JobCard


PRIORITIES = ("low", "normal", "high", "urgent")


def _apply_sla_due_filter(queryset, anchor_field: str, open_filter: Q, due: str):
    """Filter open rows by SLA-due bucket based on (anchor + sla hours)."""
    if not due:
        return queryset
    company = CompanySettings.load()
    now = timezone.now()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    week_end = now + timedelta(days=7)

    overdue_q = Q(pk__in=[])
    due_today_q = Q(pk__in=[])
    due_week_q = Q(pk__in=[])
    for prio in PRIORITIES:
        hrs = company.sla_hours_for(prio)
        overdue_q |= Q(priority=prio, **{f"{anchor_field}__lt": now - timedelta(hours=hrs)})
        due_today_q |= Q(
            priority=prio,
            **{
                f"{anchor_field}__lte": today_end - timedelta(hours=hrs),
                f"{anchor_field}__gte": now - timedelta(hours=hrs),
            },
        )
        due_week_q |= Q(
            priority=prio,
            **{
                f"{anchor_field}__lte": week_end - timedelta(hours=hrs),
                f"{anchor_field}__gte": now - timedelta(hours=hrs),
            },
        )
    if due == "overdue":
        return queryset.filter(open_filter).filter(overdue_q)
    if due == "today":
        return queryset.filter(open_filter).filter(due_today_q)
    if due == "week":
        return queryset.filter(open_filter).filter(due_week_q)
    return queryset


def _date_filter(qs, field: str, from_key: str, to_key: str, params: dict):
    created_from = params.get(from_key, "").strip()
    created_to = params.get(to_key, "").strip()
    if created_from:
        d = parse_date(created_from)
        if d:
            qs = qs.filter(**{f"{field}__date__gte": d})
    if created_to:
        d = parse_date(created_to)
        if d:
            qs = qs.filter(**{f"{field}__date__lte": d})
    return qs


def apply_job_filters(queryset, params: dict):
    q = params.get("q", "").strip()
    status = params.get("status", "").strip()
    priority = params.get("priority", "").strip()
    assigned = params.get("assigned_to", "").strip()
    schedule = params.get("schedule", "").strip()
    sort_by = params.get("sort_by", "").strip()
    order = params.get("order", "desc").strip().lower()

    if q:
        queryset = queryset.filter(
            Q(number__icontains=q)
            | Q(title__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(device_make__icontains=q)
            | Q(device_model__icontains=q)
            | Q(serial_number__icontains=q)
        )

    if status in dict(JobCard.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if priority in dict(JobCard.PRIORITY_CHOICES):
        queryset = queryset.filter(priority=priority)
    if assigned.isdigit():
        queryset = queryset.filter(assigned_to_id=int(assigned))

    queryset = _date_filter(
        queryset, "received_on", "received_from", "received_to", params
    )
    queryset = _date_filter(
        queryset, "scheduled_for", "scheduled_from", "scheduled_to", params
    )

    if schedule == "upcoming":
        now = timezone.now()
        queryset = queryset.filter(
            scheduled_for__isnull=False,
            scheduled_for__gte=now,
            scheduled_for__lte=now + timedelta(days=14),
        ).order_by("scheduled_for", "-received_on")
        return queryset

    due = params.get("due", "").strip()
    if due:
        open_filter = ~Q(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED])
        queryset = _apply_sla_due_filter(queryset, "received_on", open_filter, due)

    valid_sort = {
        "number",
        "title",
        "status",
        "priority",
        "received_on",
        "scheduled_for",
        "updated_at",
    }
    if sort_by in valid_sort:
        direction = "" if order == "asc" else "-"
        queryset = queryset.order_by(f"{direction}{sort_by}")
    else:
        queryset = queryset.order_by("-received_on")
    return queryset


def apply_ticket_filters(queryset, params: dict):
    q = params.get("q", "").strip()
    status = params.get("status", "").strip()
    priority = params.get("priority", "").strip()
    assigned = params.get("assigned_to", "").strip()
    sort_by = params.get("sort_by", "").strip()
    order = params.get("order", "desc").strip().lower()

    if q:
        queryset = queryset.filter(
            Q(reference__icontains=q)
            | Q(subject__icontains=q)
            | Q(description__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(customer__email__icontains=q)
        )
    if status in dict(SupportTicket.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if priority in dict(SupportTicket.PRIORITY_CHOICES):
        queryset = queryset.filter(priority=priority)
    if assigned.isdigit():
        queryset = queryset.filter(assigned_to_id=int(assigned))

    queryset = _date_filter(queryset, "created_at", "created_from", "created_to", params)
    queryset = _date_filter(queryset, "updated_at", "updated_from", "updated_to", params)

    due = params.get("due", "").strip()
    if due:
        open_filter = ~Q(status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED])
        queryset = _apply_sla_due_filter(queryset, "created_at", open_filter, due)

    valid_sort = {"reference", "subject", "status", "priority", "created_at", "updated_at"}
    if sort_by in valid_sort:
        direction = "" if order == "asc" else "-"
        queryset = queryset.order_by(f"{direction}{sort_by}")
    else:
        queryset = queryset.order_by("-updated_at")
    return queryset
