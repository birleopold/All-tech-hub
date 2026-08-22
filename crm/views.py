
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Max, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from billing.models import CommercialDocument
from commerce.models import Order
from core.mixins import StaffRequiredMixin
from crm.forms import CustomerForm
from crm.models import Customer


class CustomerListView(StaffRequiredMixin, ListView):
    model = Customer
    template_name = "crm/customer_list.html"
    context_object_name = "customers"
    paginate_by = 30

    def get_queryset(self):
        queryset = Customer.objects.select_related("user").annotate(
            order_count=Count("orders", distinct=True),
            job_count=Count("job_cards", distinct=True),
            latest_order=Max("orders__placed_at"),
        )
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
        if segment == "repeat":
            queryset = queryset.filter(order_count__gte=2)
        elif segment == "active":
            queryset = queryset.filter(latest_order__gte=cutoff)
        elif segment == "dormant":
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
        orders = customer.orders.exclude(status=Order.STATUS_CANCELLED)
        documents = customer.documents.filter(
            doc_type=CommercialDocument.TYPE_INVOICE
        ).exclude(
            status__in=(
                CommercialDocument.STATUS_CANCELLED,
                CommercialDocument.STATUS_DRAFT,
            )
        )
        totals = documents.aggregate(total=Sum("total"), paid=Sum("amount_paid"))
        billed = totals["total"] or Decimal("0")
        paid = totals["paid"] or Decimal("0")
        context.update(
            {
                "recent_orders": customer.orders.all()[:8],
                "recent_documents": customer.documents.all()[:8],
                "recent_jobs": customer.job_cards.select_related("assigned_to")[:8],
                "recent_tickets": customer.support_tickets.all()[:8],
                "order_count": orders.count(),
                "lifetime_order_value": orders.aggregate(total=Sum("total"))["total"]
                or Decimal("0"),
                "outstanding_balance": max(billed - paid, Decimal("0")),
            }
        )
        return context


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
