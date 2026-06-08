from urllib.parse import parse_qs

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView

from core.filters import apply_ticket_filters
from core.forms import StaffSavedSearchForm, StaffSupportTicketForm, TicketCommentForm
from core.mixins import StaffRequiredMixin
from core.models import (
    AuditEvent,
    BusinessHours,
    ContactMessage,
    StaffNotification,
    StaffSavedSearch,
    SupportTicket,
    TicketComment,
    hours_summary,
)

User = get_user_model()

KNOWN_AUDIT_VERBS = (
    "billing.document_created",
    "billing.document_saved",
    "billing.document_converted",
    "billing.payment_recorded",
    "billing.quote_internally_approved",
    "job.status_change",
    "inventory.stock_adjust",
    "inventory.job_part_use",
    "catalog.product_saved",
)


class AuditEventListView(StaffRequiredMixin, ListView):
    model = AuditEvent
    template_name = "core/audit_list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("actor").order_by("-created_at", "-id")
        verb = self.request.GET.get("verb", "").strip()
        if verb:
            qs = qs.filter(verb=verb)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(summary__icontains=q)
                | Q(verb__icontains=q)
                | Q(target_type__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["verb_filter"] = self.request.GET.get("verb") or ""
        ctx["search_q"] = self.request.GET.get("q") or ""
        ctx["known_verbs"] = KNOWN_AUDIT_VERBS
        return ctx


class SupportTicketListView(StaffRequiredMixin, ListView):
    model = SupportTicket
    template_name = "core/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 25

    def get_queryset(self):
        qs = SupportTicket.objects.select_related("customer", "assigned_to")
        return apply_ticket_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = SupportTicket.STATUS_CHOICES
        ctx["priority_choices"] = SupportTicket.PRIORITY_CHOICES
        ctx["staff_users"] = User.objects.filter(is_staff=True).order_by("username")
        ctx["saved_searches"] = StaffSavedSearch.objects.filter(
            user=self.request.user, scope=StaffSavedSearch.SCOPE_TICKETS
        )
        ctx["saved_search_scope"] = StaffSavedSearch.SCOPE_TICKETS
        ctx["open_ticket_count"] = SupportTicket.objects.exclude(
            status__in=(SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED)
        ).count()
        return ctx


class SupportTicketDetailView(StaffRequiredMixin, DetailView):
    model = SupportTicket
    template_name = "core/ticket_detail.html"
    context_object_name = "ticket"

    def get_queryset(self):
        return SupportTicket.objects.select_related("customer", "assigned_to", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["comments"] = (
            self.object.comments.select_related("author").order_by("created_at", "id")
        )
        ctx["comment_form"] = TicketCommentForm()
        return ctx


class TicketCommentCreateView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        ticket = get_object_or_404(SupportTicket, pk=pk)
        form = TicketCommentForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Comment could not be saved — please try again.")
            return redirect("staff_ticket_detail", pk=ticket.pk)
        comment = form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        comment.save()
        ticket.save(update_fields=["updated_at"])
        if not comment.is_internal and ticket.customer.email:
            from core.notifications import notify_customer_ticket_comment

            notify_customer_ticket_comment(ticket, comment)
        messages.success(request, "Comment posted.")
        return redirect("staff_ticket_detail", pk=ticket.pk)


class SupportTicketUpdateView(StaffRequiredMixin, UpdateView):
    model = SupportTicket
    form_class = StaffSupportTicketForm
    template_name = "core/ticket_form.html"

    def get_success_url(self):
        return reverse("staff_ticket_detail", kwargs={"pk": self.object.pk})


class SupportTicketCreateView(StaffRequiredMixin, CreateView):
    model = SupportTicket
    form_class = StaffSupportTicketForm
    template_name = "core/ticket_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff_ticket_detail", kwargs={"pk": self.object.pk})


class StaffNotificationListView(StaffRequiredMixin, ListView):
    model = StaffNotification
    template_name = "core/notifications.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return StaffNotification.objects.filter(recipient=self.request.user)


class MarkNotificationsReadView(StaffRequiredMixin, View):
    def post(self, request):
        StaffNotification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        nxt = request.POST.get("next") or reverse("staff_notifications")
        return redirect(nxt)


class SaveStaffSearchView(StaffRequiredMixin, View):
    def post(self, request):
        form = StaffSavedSearchForm(request.POST)
        scope = request.POST.get("scope", StaffSavedSearch.SCOPE_JOBS)
        if scope not in dict(StaffSavedSearch.SCOPE_CHOICES):
            return HttpResponseForbidden()
        if not form.is_valid():
            messages.error(request, "Could not save search.")
            return redirect(request.POST.get("next") or reverse("staff_jobs"))
        raw = form.cleaned_data["params"].lstrip("?")
        params = {k: v[0] for k, v in parse_qs(raw).items() if v and v[0]}
        StaffSavedSearch.objects.update_or_create(
            user=request.user,
            scope=scope,
            name=form.cleaned_data["name"],
            defaults={"params": params},
        )
        messages.success(request, f"Saved filter “{form.cleaned_data['name']}”.")
        return redirect(request.POST.get("next") or reverse("staff_jobs"))


class DeleteStaffSearchView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        obj = get_object_or_404(StaffSavedSearch, pk=pk, user=request.user)
        scope = obj.scope
        obj.delete()
        messages.success(request, "Saved filter removed.")
        if scope == StaffSavedSearch.SCOPE_TICKETS:
            return redirect("staff_tickets")
        return redirect("staff_jobs")


class ContactMessageListView(StaffRequiredMixin, ListView):
    model = ContactMessage
    template_name = "core/contact_list.html"
    context_object_name = "messages_list"
    paginate_by = 30

    def get_queryset(self):
        qs = ContactMessage.objects.order_by("-created_at")
        if self.request.GET.get("handled") == "0":
            qs = qs.filter(handled=False)
        elif self.request.GET.get("handled") == "1":
            qs = qs.filter(handled=True)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(subject__icontains=q)
                | Q(name__icontains=q)
                | Q(email__icontains=q)
                | Q(message__icontains=q)
            )
        return qs


class ContactMessageToggleView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        msg = get_object_or_404(ContactMessage, pk=pk)
        msg.handled = not msg.handled
        msg.save(update_fields=["handled"])
        return redirect("staff_contact_messages")


class ContactMessageConvertTicketView(StaffRequiredMixin, View):
    def post(self, request, pk: int):
        from crm.models import Customer

        msg = get_object_or_404(ContactMessage, pk=pk)
        customer, _ = Customer.objects.get_or_create(
            email=msg.email.strip().lower(),
            defaults={"name": msg.name, "phone": msg.phone},
        )
        ticket = SupportTicket.objects.create(
            customer=customer,
            created_by=request.user,
            subject=msg.subject[:200],
            description=msg.message,
            priority=SupportTicket.PRIORITY_NORMAL,
        )
        msg.handled = True
        msg.save(update_fields=["handled"])
        messages.success(
            request,
            f"Created support ticket {ticket.reference} from contact message.",
        )
        return redirect("staff_ticket_detail", pk=ticket.pk)


class BusinessHoursView(StaffRequiredMixin, View):
    template_name = "core/business_hours.html"

    def get(self, request):
        from django.shortcuts import render

        return render(request, self.template_name, {"rows": hours_summary()})

    def post(self, request):
        for wd, _label in BusinessHours.DAYS:
            is_open = bool(request.POST.get(f"is_open_{wd}"))
            open_time = request.POST.get(f"open_{wd}") or None
            close_time = request.POST.get(f"close_{wd}") or None
            note = (request.POST.get(f"note_{wd}") or "")[:160]
            BusinessHours.objects.update_or_create(
                weekday=wd,
                defaults={
                    "is_open": is_open,
                    "open_time": open_time if is_open else None,
                    "close_time": close_time if is_open else None,
                    "note": note,
                },
            )
        messages.success(request, "Business hours updated.")
        return redirect("staff_business_hours")


class StaffNotificationGoView(StaffRequiredMixin, View):
    def get(self, request, pk: int):
        n = get_object_or_404(StaffNotification, pk=pk, recipient=request.user)
        if not n.is_read:
            n.is_read = True
            n.save(update_fields=["is_read"])
        dest = request.GET.get("next") or reverse("staff_notifications")
        if not dest.startswith("/"):
            dest = reverse("staff_notifications")
        return redirect(dest)
