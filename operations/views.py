from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView

from core.audit import log_audit_event
from core.barcodes import label_payload, repeated_labels
from core.filters import apply_job_filters
from core.mixins import StaffRequiredMixin
from core.models import StaffSavedSearch
from inventory.forms import JobStockUseForm
from operations.forms import (
    JobAttachmentForm, JobCardForm, JobExpenseForm, JobHandoverForm, JobNoteForm, TimeEntryForm,
)
from operations.job_financials import job_financial_reconciliation
from operations.job_status import allowed_next_statuses
from operations.models import JobCard, JobExpense, JobHandover
from operations.pdf import pdf_response


def _safe_redirect_target(request, fallback: str):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return fallback


class JobCardListView(StaffRequiredMixin, ListView):
    model = JobCard
    template_name = "operations/job_list.html"
    context_object_name = "jobs"
    paginate_by = 20

    def get_queryset(self):
        qs = JobCard.objects.select_related("customer", "assigned_to")
        return apply_job_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model

        ctx = super().get_context_data(**kwargs)
        ctx["job_status_choices"] = JobCard.STATUS_CHOICES
        ctx["job_priority_choices"] = JobCard.PRIORITY_CHOICES
        ctx["schedule_filter"] = self.request.GET.get("schedule") or ""
        ctx["filter_params"] = self.request.GET.copy()
        ctx["staff_users"] = (
            get_user_model().objects.filter(is_staff=True).order_by("username")
        )
        ctx["saved_searches"] = StaffSavedSearch.objects.filter(
            user=self.request.user, scope=StaffSavedSearch.SCOPE_JOBS
        )
        ctx["saved_search_scope"] = StaffSavedSearch.SCOPE_JOBS
        return ctx


class TechnicianBenchView(StaffRequiredMixin, ListView):
    model = JobCard
    template_name = "operations/bench.html"
    context_object_name = "jobs"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            JobCard.objects.select_related("customer", "assigned_to")
            .exclude(status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED])
            .order_by("scheduled_for", "-priority", "-received_on")
        )
        view = self.request.GET.get("view") or "mine"
        if view == "unassigned":
            return qs.filter(assigned_to__isnull=True)
        if view == "all":
            return qs
        return qs.filter(assigned_to=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = JobCard.objects.exclude(
            status__in=[JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED]
        )
        ctx["view_mode"] = self.request.GET.get("view") or "mine"
        ctx["mine_count"] = base.filter(assigned_to=self.request.user).count()
        ctx["unassigned_count"] = base.filter(assigned_to__isnull=True).count()
        ctx["all_open_count"] = base.count()
        ctx["overdue_count"] = sum(1 for job in base if job.is_overdue)
        return ctx


class JobCardCreateView(StaffRequiredMixin, CreateView):
    model = JobCard
    form_class = JobCardForm
    template_name = "operations/job_form.html"
    success_url = reverse_lazy("staff_jobs")

    def get_initial(self):
        initial = super().get_initial()
        customer_id = (self.request.GET.get("customer") or "").strip()
        if customer_id.isdigit():
            from crm.models import Customer

            if Customer.objects.filter(pk=int(customer_id)).exists():
                initial["customer"] = int(customer_id)
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Job {self.object.number} created.")
        return response


class JobCardUpdateView(StaffRequiredMixin, UpdateView):
    model = JobCard
    form_class = JobCardForm
    template_name = "operations/job_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form._audit_user = self.request.user
        return form

    def get_success_url(self):
        return reverse_lazy("staff_job_detail", kwargs={"pk": self.object.pk})


class JobCardDetailView(StaffRequiredMixin, DetailView):
    model = JobCard
    template_name = "operations/job_detail.html"
    context_object_name = "job"

    def get_queryset(self):
        return JobCard.objects.select_related(
            "customer", "assigned_to", "related_order", "related_invoice"
        ).prefetch_related(
            "notes__author",
            "time_entries__technician",
            "attachments",
            "inventory_adjustments__product",
            "inventory_adjustments__product_variant",
            "inventory_adjustments__created_by",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["note_form"] = JobNoteForm()
        ctx["time_form"] = TimeEntryForm(initial={"technician": self.request.user.pk, "minutes": 30})
        ctx["attachment_form"] = JobAttachmentForm()
        ctx["job_stock_form"] = JobStockUseForm()
        ctx["status_events"] = list(
            self.object.status_events.select_related("actor").order_by("created_at", "id")
        )
        ctx["feedback"] = getattr(self.object, "feedback", None)
        ctx["can_record_job_handover"] = (
            self.object.status in {JobCard.STATUS_READY, JobCard.STATUS_COMPLETED}
            and not hasattr(self.object, "handover")
            and self.request.user.has_perm("operations.change_jobcard")
        )
        ctx["handover_form"] = JobHandoverForm() if ctx["can_record_job_handover"] else None
        can_view_expenses = self.request.user.has_perm(
            "operations.view_jobexpense"
        )
        ctx["can_view_job_expenses"] = can_view_expenses
        ctx["can_add_job_expense"] = self.request.user.has_perm(
            "operations.add_jobexpense"
        )
        if can_view_expenses:
            entries = self.object.expenses.select_related("recorded_by")
            ctx["job_expenses"] = entries
            ctx["recorded_direct_cost"] = entries.aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")
        else:
            ctx["job_expenses"] = []
            ctx["recorded_direct_cost"] = None
        ctx["expense_form"] = JobExpenseForm() if ctx["can_add_job_expense"] else None
        ctx["job_financial_reconciliation"] = (
            job_financial_reconciliation(self.object)
            if can_view_expenses and self.request.user.has_perm(
                "billing.view_document_margin"
            )
            else None
        )
        return ctx


class JobBenchDetailView(JobCardDetailView):
    template_name = "operations/job_bench.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        allowed = allowed_next_statuses(self.object.status)
        ctx["next_status_choices"] = [
            (value, label)
            for value, label in JobCard.STATUS_CHOICES
            if value in allowed
        ]
        return ctx


@require_POST
@transaction.atomic
def job_bench_status(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard.objects.select_for_update(), pk=pk)
    new_status = request.POST.get("status")
    note = (request.POST.get("note") or "").strip()
    valid_statuses = dict(JobCard.STATUS_CHOICES)
    if new_status not in valid_statuses:
        messages.error(request, "Choose a valid next status.")
        return redirect("staff_job_bench_detail", pk=job.pk)
    old_status = job.status
    job.status = new_status
    job._status_actor = request.user
    job._status_note = note
    try:
        job.full_clean()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_job_bench_detail", pk=job.pk)
    job.save()
    log_audit_event(
        actor=request.user,
        verb="job.status_change",
        summary=f"{job.number}: {old_status} -> {new_status}",
        target=job,
    )
    messages.success(request, f"Moved {job.number} to {valid_statuses[new_status]}.")
    return redirect("staff_job_bench_detail", pk=job.pk)


@require_POST
@transaction.atomic
def job_record_handover(request, pk: int):
    if not request.user.is_staff or not request.user.has_perm(
        "operations.change_jobcard"
    ):
        raise Http404

    job = get_object_or_404(JobCard.objects.select_for_update(), pk=pk)
    destination = reverse_lazy("staff_job_detail", kwargs={"pk": job.pk})
    if JobHandover.objects.filter(job=job).exists():
        messages.info(request, "Handover was already recorded; the original record is retained.")
        return redirect(destination)
    if job.status not in {JobCard.STATUS_READY, JobCard.STATUS_COMPLETED}:
        messages.error(request, "Finish quality assurance and mark the job ready before handover.")
        return redirect(destination)

    form = JobHandoverForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Handover not recorded. Enter the recipient, method and confirmation.")
        return redirect(destination)

    handover = form.save(commit=False)
    handover.job = job
    handover.recorded_by = request.user
    handover.full_clean()
    handover.save()
    if job.status == JobCard.STATUS_READY:
        job.status = JobCard.STATUS_COMPLETED
        job._status_actor = request.user
        job._status_note = "Staff-confirmed handover"
        job.full_clean()
        job.save()

    log_audit_event(
        actor=request.user,
        verb="job.handover_recorded",
        summary=f"{job.number}: {handover.get_method_display()}",
        target=job,
    )
    messages.success(request, "Handover recorded. The customer can see the handover date.")
    return redirect(destination)


@require_POST
def job_add_expense(request, pk: int):
    if not request.user.is_staff or not request.user.has_perm(
        "operations.add_jobexpense"
    ):
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    form = JobExpenseForm(request.POST)
    if not form.is_valid():
        messages.error(
            request, "Expense not recorded. Check its amount, reference and description."
        )
        return redirect("staff_job_detail", pk=pk)

    expense = form.save(commit=False)
    expense.job = job
    expense.recorded_by = request.user
    try:
        expense.full_clean()
        with transaction.atomic():
            expense.save()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_job_detail", pk=pk)
    except IntegrityError:
        messages.error(
            request, "This reference is already recorded for this job. "
            "Review the existing expense before entering another."
        )
        return redirect("staff_job_detail", pk=pk)
    log_audit_event(
        actor=request.user,
        verb="job.expense_recorded",
        summary=f"{job.number}: {expense.reference} {expense.amount}",
        target=expense,
    )
    messages.success(request, "Direct job expense recorded.")
    return redirect("staff_job_detail", pk=pk)


@require_POST
def job_add_note(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    form = JobNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.job = job
        note.author = request.user
        note.save()
        messages.success(request, "Note added.")
    else:
        messages.error(request, "Could not save note.")
    return redirect(_safe_redirect_target(request, reverse_lazy("staff_job_detail", kwargs={"pk": pk})))


def job_pdf_view(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(
        JobCard.objects.select_related("customer", "assigned_to"), pk=pk
    )
    return pdf_response(job, inline=True)


def job_label_sheet(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard.objects.select_related("customer", "assigned_to"), pk=pk)
    try:
        copies = int(request.GET.get("copies") or 1)
    except ValueError:
        copies = 1
    label = label_payload(
        "Job card",
        job.number,
        job.number,
        subtitle=job.title,
        meta=(
            f"{job.customer.name}"
            + (f" / {job.device_make} {job.device_model}".strip() if job.device_make or job.device_model else "")
            + (f" / SN {job.serial_number}" if job.serial_number else "")
        ),
    )
    return render(
        request,
        "core/label_sheet.html",
        {
            "title": f"Job labels - {job.number}",
            "labels": repeated_labels([label], copies),
            "back_url": reverse_lazy("staff_job_detail", kwargs={"pk": job.pk}),
        },
    )


def job_add_time(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    if request.method != "POST":
        return redirect(_safe_redirect_target(request, reverse_lazy("staff_job_detail", kwargs={"pk": pk})))
    form = TimeEntryForm(request.POST)
    if form.is_valid():
        te = form.save(commit=False)
        te.job = job
        if not te.minutes:
            te.minutes = 0
        te.save()
        messages.success(request, "Time entry added.")
    else:
        messages.error(request, "Could not save time entry.")
    return redirect(_safe_redirect_target(request, reverse_lazy("staff_job_detail", kwargs={"pk": pk})))


def job_add_attachment(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    job = get_object_or_404(JobCard, pk=pk)
    if request.method != "POST":
        return redirect(_safe_redirect_target(request, reverse_lazy("staff_job_detail", kwargs={"pk": pk})))
    form = JobAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        att = form.save(commit=False)
        att.job = job
        att.save()
        messages.success(request, "Photo uploaded.")
    else:
        messages.error(request, "Could not save the upload — check the file and try again.")
    return redirect(_safe_redirect_target(request, reverse_lazy("staff_job_detail", kwargs={"pk": pk})))


class JobScheduleCalendarView(StaffRequiredMixin, ListView):
    template_name = "operations/job_calendar.html"
    context_object_name = "rows"

    def _week_start(self, anchor: date) -> date:
        return anchor - timedelta(days=anchor.weekday())

    def get_queryset(self):
        return JobCard.objects.none()

    def get_context_data(self, **kwargs):
        from django.contrib.auth import get_user_model

        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        view_mode = (self.request.GET.get("view") or "week").strip().lower()
        if view_mode not in ("week", "month"):
            view_mode = "week"
        if view_mode == "month":
            ctx.update(self._month_context(today))
            ctx["view_mode"] = "month"
            return ctx
        raw = (self.request.GET.get("week") or "").strip()
        anchor = parse_date(raw) or today
        week_start = self._week_start(anchor)
        week_end = week_start + timedelta(days=7)

        tz = timezone.get_current_timezone()
        start_dt = datetime.combine(week_start, time.min, tzinfo=tz)
        end_dt = datetime.combine(week_end, time.min, tzinfo=tz)

        days = [week_start + timedelta(days=i) for i in range(7)]
        User = get_user_model()
        technicians = list(User.objects.filter(is_staff=True).order_by("username"))

        jobs = (
            JobCard.objects.filter(
                scheduled_for__isnull=False,
                scheduled_for__gte=start_dt,
                scheduled_for__lt=end_dt,
            )
            .exclude(status=JobCard.STATUS_CANCELLED)
            .select_related("customer", "assigned_to")
            .order_by("scheduled_for")
        )

        rows = []
        unassigned_bucket = {d: [] for d in days}
        per_tech = {u.id: {d: [] for d in days} for u in technicians}
        for j in jobs:
            local = timezone.localtime(j.scheduled_for)
            day_key = local.date()
            if day_key not in unassigned_bucket:
                continue
            entry = {
                "job": j,
                "label_time": local.strftime("%H:%M"),
                "until": (
                    timezone.localtime(j.scheduled_until).strftime("%H:%M")
                    if j.scheduled_until else ""
                ),
            }
            if j.assigned_to_id and j.assigned_to_id in per_tech:
                per_tech[j.assigned_to_id][day_key].append(entry)
            else:
                unassigned_bucket[day_key].append(entry)

        for u in technicians:
            rows.append(
                {
                    "label": u.get_username(),
                    "is_unassigned": False,
                    "days": [
                        {"date": d, "items": per_tech[u.id][d]} for d in days
                    ],
                }
            )
        rows.append(
            {
                "label": "Unassigned",
                "is_unassigned": True,
                "days": [
                    {"date": d, "items": unassigned_bucket[d]} for d in days
                ],
            }
        )

        ctx["rows"] = rows
        ctx["days"] = days
        ctx["week_start"] = week_start
        ctx["week_end"] = week_end - timedelta(days=1)
        ctx["prev_week"] = (week_start - timedelta(days=7)).isoformat()
        ctx["next_week"] = (week_start + timedelta(days=7)).isoformat()
        ctx["today"] = today
        ctx["this_week"] = today.isoformat()
        ctx["view_mode"] = "week"
        return ctx

    def _month_context(self, today: date) -> dict:
        raw = (self.request.GET.get("month") or "").strip()
        anchor = parse_date(raw) or today
        first = anchor.replace(day=1)
        if first.month == 12:
            next_first = first.replace(year=first.year + 1, month=1)
        else:
            next_first = first.replace(month=first.month + 1)
        last = next_first - timedelta(days=1)
        grid_start = self._week_start(first)
        end_offset = 6 - last.weekday()
        grid_end = last + timedelta(days=end_offset)

        tz = timezone.get_current_timezone()
        start_dt = datetime.combine(grid_start, time.min, tzinfo=tz)
        end_dt = datetime.combine(grid_end + timedelta(days=1), time.min, tzinfo=tz)

        jobs = (
            JobCard.objects.filter(
                scheduled_for__isnull=False,
                scheduled_for__gte=start_dt,
                scheduled_for__lt=end_dt,
            )
            .exclude(status=JobCard.STATUS_CANCELLED)
            .select_related("customer", "assigned_to")
            .order_by("scheduled_for")
        )
        by_day = {}
        for j in jobs:
            local = timezone.localtime(j.scheduled_for)
            by_day.setdefault(local.date(), []).append(j)

        days = []
        cursor = grid_start
        while cursor <= grid_end:
            days.append(
                {
                    "date": cursor,
                    "in_month": cursor.month == first.month,
                    "is_today": cursor == today,
                    "jobs": by_day.get(cursor, []),
                }
            )
            cursor += timedelta(days=1)

        prev_month = (first - timedelta(days=1)).replace(day=1)
        next_month = next_first
        return {
            "month_days": days,
            "month_first": first,
            "month_last": last,
            "prev_month": prev_month.isoformat(),
            "next_month": next_month.isoformat(),
            "this_month": today.isoformat(),
            "today": today,
        }


@require_POST
def staff_job_reschedule(request, pk: int):
    """AJAX/JSON endpoint: change scheduled_for/until for a job from the calendar."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)
    job = get_object_or_404(JobCard, pk=pk)
    new_start_raw = (request.POST.get("scheduled_for") or "").strip()
    new_end_raw = (request.POST.get("scheduled_until") or "").strip()
    if not new_start_raw:
        return JsonResponse({"ok": False, "error": "Missing scheduled_for"}, status=400)
    try:
        start_dt = datetime.fromisoformat(new_start_raw)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Invalid scheduled_for"}, status=400)
    end_dt = None
    if new_end_raw:
        try:
            end_dt = datetime.fromisoformat(new_end_raw)
        except ValueError:
            return JsonResponse({"ok": False, "error": "Invalid scheduled_until"}, status=400)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)
    if end_dt and timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt)
    job.scheduled_for = start_dt
    job.scheduled_until = end_dt
    try:
        job.full_clean()
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
    job.save()
    return JsonResponse(
        {
            "ok": True,
            "scheduled_for": timezone.localtime(job.scheduled_for).isoformat(),
            "scheduled_until": (
                timezone.localtime(job.scheduled_until).isoformat()
                if job.scheduled_until else None
            ),
        }
    )
