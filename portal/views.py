import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView
from django.views.generic.edit import FormView

from billing.models import CommercialDocument, PaymentSubmission
from billing.pdf import pdf_response as document_pdf_response
from catalog.models import Product, ProductSerial, WishlistItem
from commerce.models import Order
from core.forms import PortalSupportTicketForm, PortalTicketReplyForm
from core.models import Announcement, KnowledgeArticle, SupportTicket, TicketComment
from crm.models import Customer, CustomerAddress
from operations.models import JobCard, JobFeedback, JobNote, JobStatusEvent
from portal.forms import CustomerAddressForm, CustomerSignUpForm, PortalRepairIntakeForm

logger = logging.getLogger(__name__)
EMAIL_VERIFICATION_SALT = "alltech.portal.email-verification"


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
        ctx["outstanding_invoices"] = list(
            inv.order_by("due_date", "-issue_date")[:5]
        )
        ctx["pending_payment_count"] = PaymentSubmission.objects.filter(
            document__customer=customer,
            status=PaymentSubmission.STATUS_PENDING,
        ).count()
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
        unsafe_delivery_backends = {
            "django.core.mail.backends.console.EmailBackend",
            "django.core.mail.backends.dummy.EmailBackend",
            "django.core.mail.backends.filebased.EmailBackend",
            "django.core.mail.backends.locmem.EmailBackend",
        }
        if not settings.DEBUG and settings.EMAIL_BACKEND in unsafe_delivery_backends:
            logger.error("customer_portal_email_delivery_is_not_configured")
            form.add_error(
                None,
                "Customer registration is temporarily unavailable. Please contact us.",
            )
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                user = form.save()
                token = signing.dumps(
                    {"user_id": user.pk, "email": user.email},
                    salt=EMAIL_VERIFICATION_SALT,
                )
                verify_url = self.request.build_absolute_uri(
                    reverse("portal_verify_email", kwargs={"token": token})
                )
                send_mail(
                    "Verify your LEOSOFT customer account",
                    (
                        "Welcome to LEOSOFT. Verify your email to securely access "
                        "your orders, repairs, invoices and warranties:\n\n"
                        f"{verify_url}\n\n"
                        "If you did not request this account, ignore this email."
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
        except Exception:
            logger.exception("customer_portal_verification_email_failed")
            form.add_error(
                None,
                "We could not send your verification email. Please try again or contact us.",
            )
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Check your email and open the verification link to activate your account.",
        )
        return redirect("portal_login")


@transaction.atomic
def verify_customer_email(request, token: str):
    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=getattr(settings, "PORTAL_EMAIL_VERIFICATION_MAX_AGE", 86400),
        )
    except signing.BadSignature:
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("portal_login")

    User = get_user_model()
    user = get_object_or_404(
        User.objects.select_for_update(),
        pk=payload.get("user_id"),
        email__iexact=payload.get("email", ""),
    )
    customers = list(
        Customer.objects.select_for_update().filter(email__iexact=user.email)[:2]
    )
    if len(customers) != 1:
        messages.error(request, "Your customer record needs a support review.")
        return redirect("portal_login")
    customer = customers[0]
    if customer.user_id and customer.user_id != user.pk:
        messages.error(request, "This customer account is already linked to another user.")
        return redirect("portal_login")

    if user.is_active and customer.user_id == user.pk:
        messages.info(request, "This account is already verified. Please sign in.")
        return redirect("portal_login")

    if customer.user_id != user.pk:
        customer.user = user
        customer.save(update_fields=["user", "updated_at"])
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Your email is verified and your customer portal is ready.")
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
    related_tickets = list(
        SupportTicket.objects.filter(customer=customer, related_job=job)
        .order_by("-updated_at")[:5]
    )
    return render(
        request,
        "portal/job_detail.html",
        {
            "job": job,
            "related_tickets": related_tickets,
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


@require_POST
def my_document_payment(request, pk: int):
    customer = _customer_for_request(request)
    if customer is None:
        return redirect("portal_login")
    document = get_object_or_404(
        CommercialDocument.objects.select_related("customer"),
        pk=pk,
        customer=customer,
    )
    if (
        not document.supports_payment_request
        or document.status in (
            CommercialDocument.STATUS_CANCELLED,
            CommercialDocument.STATUS_EXPIRED,
        )
        or document.balance_due <= 0
    ):
        messages.error(request, "This document is not available for payment.")
        return redirect("portal_documents")
    if not document.payment_request_token:
        document.ensure_payment_request_token()
        document.save(update_fields=["payment_request_token", "updated_at"])
    return redirect(
        "payment_request_portal",
        token=document.payment_request_token,
    )


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

    def get_initial(self):
        initial = super().get_initial()
        customer = _customer_for_request(self.request)
        if customer is None:
            return initial

        order_id = (self.request.GET.get("order") or "").strip()
        product_id = (self.request.GET.get("product") or "").strip()
        action = (self.request.GET.get("action") or "").strip()
        if order_id.isdigit():
            order = Order.objects.filter(
                pk=int(order_id),
                customer=customer,
            ).first()
            if order is not None:
                initial["related_order"] = order.pk
                initial["subject"] = f"Support for order {order.reference}"[:200]
                product = None
                if product_id.isdigit():
                    product = Product.objects.filter(
                        pk=int(product_id),
                        order_lines__order=order,
                    ).first()
                    if product is not None:
                        initial["related_product"] = product.pk

                if (
                    action == "return"
                    and order.status
                    in (Order.STATUS_DELIVERED, Order.STATUS_FULFILLED)
                ):
                    initial["category"] = SupportTicket.CATEGORY_RMA
                    item_name = product.name if product is not None else order.reference
                    initial["subject"] = f"Return request: {item_name}"[:200]

        job_id = (self.request.GET.get("job") or "").strip()
        if job_id.isdigit():
            job = JobCard.objects.filter(pk=int(job_id), customer=customer).first()
            if job is not None:
                initial["related_job"] = job.pk
                if not initial.get("subject"):
                    initial["subject"] = f"Support for repair {job.number}"[:200]

        document_id = (self.request.GET.get("document") or "").strip()
        if document_id.isdigit():
            document = CommercialDocument.objects.filter(
                pk=int(document_id), customer=customer
            ).first()
            if document is not None:
                initial["related_document"] = document.pk
                if document.order_id and not initial.get("related_order"):
                    initial["related_order"] = document.order_id
                initial["category"] = SupportTicket.CATEGORY_BILLING
                initial["subject"] = f"Question about {document.number}"[:200]

        serial_id = (self.request.GET.get("serial") or "").strip()
        if not serial_id.isdigit():
            return initial

        serial = (
            ProductSerial.objects.filter(pk=int(serial_id), sold_to=customer)
            .select_related("product")
            .first()
        )
        if serial is None:
            return initial

        initial["related_serial"] = serial.pk
        initial["related_product"] = serial.product_id
        if serial.is_under_warranty:
            initial["category"] = SupportTicket.CATEGORY_WARRANTY
            initial["subject"] = (
                f"Warranty claim: {serial.product.name} "
                f"({serial.serial_number})"
            )[:200]
        else:
            initial["category"] = SupportTicket.CATEGORY_GENERAL
            initial["subject"] = (
                f"Repair support: {serial.product.name} "
                f"({serial.serial_number})"
            )[:200]
        return initial

    def form_valid(self, form):
        customer = _customer_for_request(self.request)
        ticket = form.save(commit=False)
        if (
            ticket.category == SupportTicket.CATEGORY_WARRANTY
            and ticket.related_serial_id
        ):
            existing = (
                SupportTicket.objects.filter(
                    customer=customer,
                    category=SupportTicket.CATEGORY_WARRANTY,
                    related_serial_id=ticket.related_serial_id,
                )
                .exclude(
                    status__in=(
                        SupportTicket.STATUS_RESOLVED,
                        SupportTicket.STATUS_CLOSED,
                    )
                )
                .first()
            )
            if existing is not None:
                messages.info(
                    self.request,
                    f"An active warranty claim already exists: {existing.reference}.",
                )
                return redirect("portal_ticket_detail", pk=existing.pk)

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
