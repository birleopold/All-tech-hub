from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, TemplateView
from django.views.generic.edit import FormView

from billing.models import CommercialDocument
from billing.pdf import pdf_response as document_pdf_response
from catalog.models import Product, WishlistItem
from commerce.models import Order
from core.forms import PortalSupportTicketForm, PortalTicketReplyForm
from core.models import Announcement, KnowledgeArticle, SupportTicket, TicketComment
from crm.models import Customer, CustomerAddress
from operations.models import JobCard, JobFeedback, JobNote, JobStatusEvent
from portal.forms import CustomerAddressForm, CustomerSignUpForm, PortalRepairIntakeForm


class PortalHomeView(TemplateView):
    template_name = "portal/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx["announcements"] = (
            Announcement.objects.filter(is_active=True)
            .filter(Q(active_from__isnull=True) | Q(active_from__lte=today))
            .filter(Q(active_until__isnull=True) | Q(active_until__gte=today))[:8]
        )
        customer = _customer_for_request(self.request)
        ctx["portal_customer"] = customer
        if customer is None:
            return ctx
        open_statuses = [
            s
            for s, _ in JobCard.STATUS_CHOICES
            if s not in (JobCard.STATUS_COMPLETED, JobCard.STATUS_CANCELLED)
        ]
        ctx["open_jobs_count"] = JobCard.objects.filter(
            customer=customer, status__in=open_statuses
        ).count()
        ctx["recent_orders"] = list(
            Order.objects.filter(customer=customer).order_by("-placed_at")[:5]
        )
        inv = CommercialDocument.objects.filter(
            customer=customer,
            doc_type=CommercialDocument.TYPE_INVOICE,
        ).exclude(
            status__in=(
                CommercialDocument.STATUS_PAID,
                CommercialDocument.STATUS_CANCELLED,
            )
        )
        balance = Decimal("0")
        for d in inv.only("total", "amount_paid"):
            due = (d.total - d.amount_paid).quantize(Decimal("0.01"))
            if due > 0:
                balance += due
        ctx["unpaid_invoice_balance"] = balance
        ctx["recent_jobs"] = list(
            JobCard.objects.filter(customer=customer).order_by("-received_on")[:5]
        )
        ctx["open_tickets_count"] = SupportTicket.objects.filter(
            customer=customer
        ).exclude(
            status__in=(SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED)
        ).count()
        ctx["recent_tickets"] = list(
            SupportTicket.objects.filter(customer=customer).order_by("-updated_at")[:5]
        )
        return ctx


class KnowledgeBaseListView(ListView):
    """Public knowledge base (no login required)."""

    template_name = "portal/kb_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        qs = KnowledgeArticle.objects.filter(is_published=True)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
        return qs.order_by("sort_order", "title")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_q"] = self.request.GET.get("q") or ""
        return ctx


def kb_article_detail(request, slug: str):
    article = get_object_or_404(
        KnowledgeArticle.objects.filter(is_published=True),
        slug=slug,
    )
    return render(request, "portal/kb_detail.html", {"article": article})


class CustomerSignUpView(FormView):
    template_name = "portal/signup.html"
    form_class = CustomerSignUpForm

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Welcome! Your customer portal is ready.")
        return redirect("portal_home")


def _customer_for_request(request) -> Customer | None:
    if not request.user.is_authenticated:
        return None
    return getattr(request.user, "customer_profile", None)


def _safe_portal_next(request, candidate: str | None, fallback: str) -> str:
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


class MyJobsView(ListView):
    template_name = "portal/jobs.html"
    context_object_name = "jobs"
    paginate_by = 20

    def get_queryset(self):
        customer = _customer_for_request(self.request)
        if customer is None:
            return JobCard.objects.none()
        return JobCard.objects.filter(customer=customer).order_by("-received_on")

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)


def my_job_detail(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    job = get_object_or_404(
        JobCard.objects.select_related("customer", "assigned_to").prefetch_related(
            "attachments"
        ),
        pk=pk,
    )
    if job.customer_id != customer.id:
        raise Http404
    notes = JobNote.objects.filter(job=job, is_internal=False).select_related("author").order_by("created_at")
    attachments = list(
        job.attachments.filter(show_to_customer=True).order_by("-created_at")
    )
    status_events = list(
        JobStatusEvent.objects.filter(job=job).order_by("created_at", "id")
    )
    timeline = [
        {"label": "Received", "dt": job.received_on},
    ]
    if job.estimated_completion:
        timeline.append({"label": "Estimated completion", "dt": job.estimated_completion})
    if job.closed_on:
        timeline.append({"label": "Closed", "dt": job.closed_on})
    feedback = getattr(job, "feedback", None)
    return render(
        request,
        "portal/job_detail.html",
        {
            "job": job,
            "notes": notes,
            "attachments": attachments,
            "timeline": timeline,
            "status_events": status_events,
            "feedback": feedback,
            "can_leave_feedback": (
                job.status == JobCard.STATUS_COMPLETED and feedback is None
            ),
        },
    )


def job_feedback_view(request, pk: int):
    """Customer rating page — accessible from portal or a public token URL."""

    job = get_object_or_404(JobCard.objects.select_related("customer"), pk=pk)
    customer = _customer_for_request(request)
    if customer is None or job.customer_id != customer.id:
        return redirect("portal_login")
    if job.status != JobCard.STATUS_COMPLETED:
        messages.info(request, "Feedback is available once the job is completed.")
        return redirect("portal_job_detail", pk=job.pk)
    if hasattr(job, "feedback"):
        messages.info(request, "You have already left feedback for this job.")
        return redirect("portal_job_detail", pk=job.pk)
    if request.method == "POST":
        try:
            rating = int(request.POST.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0
        comment = (request.POST.get("comment") or "").strip()
        if rating < 1 or rating > 5:
            messages.error(request, "Please choose a rating between 1 and 5 stars.")
        else:
            JobFeedback.objects.create(
                job=job, rating=rating, comment=comment[:2000]
            )
            messages.success(request, "Thanks for the feedback!")
            return redirect("portal_job_detail", pk=job.pk)
    return render(request, "portal/job_feedback.html", {"job": job})


class MyDocumentsView(ListView):
    template_name = "portal/documents.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        customer = _customer_for_request(self.request)
        if customer is None:
            return CommercialDocument.objects.none()
        return CommercialDocument.objects.filter(customer=customer).order_by("-issue_date", "-id")

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)


def my_document_pdf(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    doc = get_object_or_404(CommercialDocument, pk=pk)
    if doc.customer_id != customer.id:
        raise Http404
    return document_pdf_response(doc, inline=True)


class MyOrdersView(ListView):
    template_name = "portal/orders.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        customer = _customer_for_request(self.request)
        if customer is None:
            return Order.objects.none()
        return Order.objects.filter(customer=customer).order_by("-placed_at")

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)


def my_order_detail(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related(
            "lines__product",
            "lines__product_variant",
            "documents",
            "status_events",
        ),
        pk=pk,
    )
    if order.customer_id != customer.id:
        raise Http404
    docs = CommercialDocument.objects.filter(order=order, customer=customer).order_by("-issue_date", "-id")
    return render(
        request,
        "portal/order_detail.html",
        {
            "order": order,
            "documents": docs,
            "shipment": getattr(order, "shipment", None),
            "status_events": order.status_events.filter(visible_to_customer=True),
        },
    )


class MyTicketsView(ListView):
    template_name = "portal/tickets.html"
    context_object_name = "tickets"
    paginate_by = 20

    def get_queryset(self):
        customer = _customer_for_request(self.request)
        if customer is None:
            return SupportTicket.objects.none()
        return SupportTicket.objects.filter(customer=customer).order_by("-updated_at")

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)


class PortalTicketCreateView(FormView):
    template_name = "portal/ticket_form.html"
    form_class = PortalSupportTicketForm

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["customer"] = _customer_for_request(self.request)
        return kwargs

    def form_valid(self, form):
        customer = _customer_for_request(self.request)
        ticket = form.save(commit=False)
        ticket.customer = customer
        ticket.created_by = self.request.user
        ticket.save()
        messages.success(
            self.request,
            f"Support request {ticket.reference} submitted. We will respond by email.",
        )
        return redirect("portal_tickets")


class PortalRepairIntakeView(FormView):
    template_name = "portal/repair_intake.html"
    form_class = PortalRepairIntakeForm

    def dispatch(self, request, *args, **kwargs):
        if _customer_for_request(request) is None:
            return redirect("portal_login")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        customer = _customer_for_request(self.request)
        job = JobCard.objects.create(
            customer=customer,
            title=form.cleaned_data["title"],
            device_type=form.cleaned_data.get("device_type") or "",
            device_make=form.cleaned_data.get("device_make") or "",
            device_model=form.cleaned_data.get("device_model") or "",
            serial_number=form.cleaned_data.get("serial_number") or "",
            problem_reported=form.cleaned_data["problem_reported"],
            status=JobCard.STATUS_INTAKE,
        )
        messages.success(
            self.request,
            f"Repair request received — job {job.number}. We will contact you when it is checked in.",
        )
        return redirect("portal_job_detail", pk=job.pk)


def my_wishlist(request):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    items = (
        WishlistItem.objects.filter(customer=customer)
        .select_related("product", "product__category")
    )
    return render(request, "portal/wishlist.html", {"items": items})


def wishlist_add(request, product_id: int):
    if request.method != "POST":
        return redirect("portal_wishlist")
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    product = get_object_or_404(Product, pk=product_id, is_published=True)
    _, created = WishlistItem.objects.get_or_create(customer=customer, product=product)
    if created:
        messages.success(request, f"Added “{product.name}” to your wishlist.")
    else:
        messages.info(request, f"“{product.name}” is already on your wishlist.")
    nxt = _safe_portal_next(
        request, request.POST.get("next"), product.get_absolute_url()
    )
    return redirect(nxt)


def wishlist_remove(request, product_id: int):
    if request.method != "POST":
        return redirect("portal_wishlist")
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    WishlistItem.objects.filter(customer=customer, product_id=product_id).delete()
    messages.info(request, "Removed from wishlist.")
    return redirect(
        _safe_portal_next(request, request.POST.get("next"), "portal_wishlist")
    )


def my_addresses(request):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    if request.method == "POST" and request.POST.get("action") == "delete":
        addr_id = request.POST.get("address_id")
        CustomerAddress.objects.filter(pk=addr_id, customer=customer).delete()
        messages.success(request, "Address removed.")
        return redirect("portal_addresses")
    if request.method == "POST":
        form = CustomerAddressForm(request.POST)
        if form.is_valid():
            addr = form.save(commit=False)
            addr.customer = customer
            addr.save()
            messages.success(request, "Address saved.")
            return redirect("portal_addresses")
    else:
        form = CustomerAddressForm()
    addresses = customer.addresses.all().order_by("-is_default", "label")
    return render(
        request,
        "portal/addresses.html",
        {"addresses": addresses, "form": form},
    )


def my_address_edit(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    address = get_object_or_404(CustomerAddress, pk=pk, customer=customer)
    if request.method == "POST":
        form = CustomerAddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated.")
            return redirect("portal_addresses")
    else:
        form = CustomerAddressForm(instance=address)
    return render(
        request,
        "portal/address_edit.html",
        {"form": form, "address": address},
    )


def my_ticket_detail(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    ticket = get_object_or_404(SupportTicket, pk=pk, customer=customer)
    closed = ticket.status in (SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED)
    reply_form = PortalTicketReplyForm()
    if request.method == "POST" and not closed:
        reply_form = PortalTicketReplyForm(request.POST)
        if reply_form.is_valid():
            comment = reply_form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            comment.is_internal = False
            comment.save()
            ticket.save(update_fields=["updated_at"])
            from core.notifications import notify_staff_ticket_reply

            notify_staff_ticket_reply(ticket, comment)
            messages.success(request, "Reply sent — our team has been notified.")
            return redirect("portal_ticket_detail", pk=ticket.pk)
    comments = (
        TicketComment.objects.filter(ticket=ticket, is_internal=False)
        .select_related("author")
        .order_by("created_at", "id")
    )
    return render(
        request,
        "portal/ticket_detail.html",
        {
            "ticket": ticket,
            "comments": comments,
            "reply_form": reply_form,
            "can_reply": not closed,
        },
    )

