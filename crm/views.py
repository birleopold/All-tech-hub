
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django.shortcuts import get_object_or_404, redirect

from billing.models import AccountPayment, CommercialDocument, DocumentPayment
from commerce.models import Order
from core.mixins import StaffRequiredMixin
from core.models import ContactMessage
from crm.forms import CustomerForm
from crm.models import Customer
from loyalty.models import LoyaltyAccount
from loyalty.services import redeem_loyalty_points
from marketing.models import MarketingLead


class CustomerListView(StaffRequiredMixin, ListView):
    model = Customer
    template_name = "crm/customer_list.html"
    context_object_name = "customers"
    paginate_by = 30

    def get_queryset(self):
        queryset = Customer.objects.select_related("user")
        can_orders = self.request.user.has_perm("commerce.view_order")
        can_jobs = self.request.user.has_perm("operations.view_jobcard")
        if can_orders:
            queryset = queryset.annotate(
                order_count=Count("orders", distinct=True),
                latest_order=Max("orders__placed_at"),
            )
        if can_jobs:
            queryset = queryset.annotate(job_count=Count("job_cards", distinct=True))
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(company_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        segment = self.request.GET.get("segment", "")
        cutoff = timezone.now() - timedelta(days=90)
        if segment == "repeat" and can_orders:
            queryset = queryset.filter(order_count__gte=2)
        elif segment == "active" and can_orders:
            queryset = queryset.filter(latest_order__gte=cutoff)
        elif segment == "dormant" and can_orders:
            queryset = queryset.filter(latest_order__lt=cutoff)
        elif segment == "unlinked":
            queryset = queryset.filter(user__isnull=True)
        return queryset.order_by("name", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "query": self.request.GET.get("q", "").strip(),
                "segment": self.request.GET.get("segment", ""),
                "customer_count": Customer.objects.count(),
                "verified_count": Customer.objects.filter(user__isnull=False).count(),
                "can_view_orders": self.request.user.has_perm("commerce.view_order"),
                "can_view_jobs": self.request.user.has_perm("operations.view_jobcard"),
            }
        )
        return context


class CustomerDetailView(StaffRequiredMixin, DetailView):
    model = Customer
    template_name = "crm/customer_detail.html"
    context_object_name = "customer"

    def get_queryset(self):
        return Customer.objects.select_related("user").prefetch_related("addresses")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object
        can_orders = self.request.user.has_perm("commerce.view_order")
        can_documents = self.request.user.has_perm("billing.view_commercialdocument")
        can_finance = self.request.user.has_perm("billing.view_documentpayment")
        can_jobs = self.request.user.has_perm("operations.view_jobcard")
        can_tickets = self.request.user.has_perm("core.view_supportticket")
        can_leads = self.request.user.has_perm("marketing.view_marketinglead")
        can_contacts = self.request.user.has_perm("core.view_contactmessage")
        can_serials = self.request.user.has_perm("catalog.view_productserial")
        orders = customer.orders.exclude(status=Order.STATUS_CANCELLED)
        documents = customer.documents.filter(
            doc_type=CommercialDocument.TYPE_INVOICE
        ).exclude(
            status__in=(
                CommercialDocument.STATUS_CANCELLED,
                CommercialDocument.STATUS_DRAFT,
            )
        )
        totals = documents.aggregate(total=Sum("total"), paid=Sum("amount_paid")) if can_finance else {}
        billed = totals.get("total") or Decimal("0")
        paid = totals.get("paid") or Decimal("0")
        # A matching email is an identity hint, not proof of customer
        # ownership. Never attribute unlinked leads/messages to one of
        # several legacy CRM records sharing the same address.
        duplicate_email = bool(
            customer.email and Customer.objects.filter(
                email__iexact=customer.email
            ).exclude(pk=customer.pk).exists()
        )
        identity_is_unambiguous = bool(customer.email and not duplicate_email)
        enquiries = MarketingLead.objects.filter(email__iexact=customer.email).select_related(
            "product", "quoted_document", "assigned_to"
        )[:12] if identity_is_unambiguous and can_leads else MarketingLead.objects.none()
        messages_received = ContactMessage.objects.filter(email__iexact=customer.email).select_related(
            "product"
        )[:12] if identity_is_unambiguous and can_contacts else ContactMessage.objects.none()
        timeline = []
        for order in customer.orders.all()[:8] if can_orders else []:
            timeline.append({"kind": "Order", "label": order.reference, "occurred_at": order.placed_at, "status": order.get_status_display(), "url": reverse("staff_order_detail", args=[order.pk])})
        for document in customer.documents.all()[:8] if can_documents else []:
            timeline.append({"kind": document.get_doc_type_display(), "label": document.number, "occurred_at": document.created_at, "status": document.get_status_display(), "url": reverse("staff_document_view", args=[document.pk])})
        for job in customer.job_cards.all()[:8] if can_jobs else []:
            timeline.append({
                "kind": "Repair", "label": job.number,
                "occurred_at": job.received_on,
                "status": job.get_status_display(),
                "url": reverse("staff_job_detail", args=[job.pk]),
            })
        for ticket in customer.support_tickets.all()[:8] if can_tickets else []:
            timeline.append({
                "kind": "Support", "label": ticket.reference,
                "occurred_at": ticket.updated_at,
                "status": ticket.get_status_display(),
                "url": reverse("staff_ticket_detail", args=[ticket.pk]),
            })
        for lead in enquiries:
            timeline.append({"kind": "Product enquiry", "label": lead.product.name if lead.product_id else lead.name, "occurred_at": lead.created_at, "status": lead.get_status_display(), "url": reverse("staff_marketing_lead_edit", args=[lead.pk])})
        for contact in messages_received:
            timeline.append({"kind": "Customer message", "label": contact.subject, "occurred_at": contact.created_at, "status": "Handled" if contact.handled else "Needs response", "url": reverse("staff_contact_messages")})
        timeline.sort(key=lambda event: event["occurred_at"], reverse=True)
        recent_payments = (
            DocumentPayment.objects.filter(document__customer=customer)
            .select_related("document").order_by("-recorded_at")[:8]
            if can_finance else []
        )
        account_payments = (
            AccountPayment.objects.filter(customer=customer).order_by("-recorded_at")[:8]
            if can_finance else []
        )
        serials = (
            customer.purchased_serials.select_related("product").order_by("-sold_at")[:8]
            if can_serials else []
        )
        context.update(
            {
                "recent_orders": customer.orders.all()[:8] if can_orders else [],
                "recent_documents": customer.documents.all()[:8] if can_documents else [],
                "recent_jobs": customer.job_cards.select_related("assigned_to")[:8] if can_jobs else [],
                "recent_tickets": customer.support_tickets.all()[:8] if can_tickets else [],
                "recent_enquiries": enquiries,
                "recent_payments": recent_payments,
                "recent_account_payments": account_payments,
                "purchased_serials": serials,
                "customer_access": {
                    "orders": can_orders, "documents": can_documents,
                    "finance": can_finance, "jobs": can_jobs, "tickets": can_tickets,
                    "leads": can_leads, "serials": can_serials,
                },
                "customer_timeline": timeline[:24],
                "customer_identity_review_required": duplicate_email,
                "loyalty_account": LoyaltyAccount.objects.filter(customer=customer).first()
                if self.request.user.has_perm("loyalty.view_loyaltyaccount") else None,
                "available_credits": customer.credits.filter(status="open")
                if can_finance else [],
                "order_count": orders.count() if can_orders else 0,
                "lifetime_order_value": (orders.aggregate(total=Sum("total"))["total"]
                or Decimal("0")) if can_orders else Decimal("0"),
                "outstanding_balance": max(billed - paid, Decimal("0"))
                if can_finance else Decimal("0"),
            }
        )
        return context


class LoyaltyRedeemView(StaffRequiredMixin, View):
    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        try:
            _, credit = redeem_loyalty_points(customer, request.POST.get("points"), actor=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, f"Reward redeemed: {credit.amount:,.2f} account credit ({credit.reference}).")
        return redirect("staff_customer_detail", pk=customer.pk)


class CustomerCreateView(StaffRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Customer record created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff_customer_detail", kwargs={"pk": self.object.pk})


class CustomerUpdateView(StaffRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Customer record updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("staff_customer_detail", kwargs={"pk": self.object.pk})
