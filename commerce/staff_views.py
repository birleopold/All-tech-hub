from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView

from billing.models import CommercialDocument, CommercialLine, allocate_document_number
from commerce.models import Order
from core.mixins import StaffRequiredMixin


class StaffOrderListView(StaffRequiredMixin, ListView):
    model = Order
    template_name = "commerce/staff_order_list.html"
    context_object_name = "orders"
    paginate_by = 25

    def get_queryset(self):
        qs = Order.objects.select_related("customer").order_by("-placed_at")
        st = self.request.GET.get("status")
        if st in dict(Order.STATUS_CHOICES):
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order_status_choices"] = Order.STATUS_CHOICES
        return ctx


class StaffOrderDetailView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = "commerce/staff_order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("customer").prefetch_related(
            "lines__product", "lines__product_variant", "documents"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order_status_choices"] = Order.STATUS_CHOICES
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        status = request.POST.get("status")
        if status in dict(Order.STATUS_CHOICES):
            self.object.status = status
        note = request.POST.get("staff_note")
        if note is not None:
            self.object.staff_note = note.strip()
        self.object.save(update_fields=["status", "staff_note", "updated_at"])
        messages.success(request, "Order updated.")
        return redirect("staff_order_detail", pk=self.object.pk)


@transaction.atomic
def staff_create_invoice_from_order(request, pk: int):
    if not request.user.is_staff:
        from django.http import Http404

        raise Http404
    order = get_object_or_404(
        Order.objects.prefetch_related("lines__product", "lines__product_variant"), pk=pk
    )
    if request.method != "POST":
        return redirect("staff_order_detail", pk=pk)
    existing = order.documents.filter(
        doc_type=CommercialDocument.TYPE_INVOICE
    ).first()
    if existing:
        messages.info(
            request,
            f"This order already has invoice {existing.number}.",
        )
        return redirect("staff_document_edit", pk=existing.pk)
    inv = CommercialDocument.objects.create(
        doc_type=CommercialDocument.TYPE_INVOICE,
        number=allocate_document_number("INV"),
        customer=order.customer,
        status=CommercialDocument.STATUS_DRAFT,
        tax_rate=order.tax_rate,
        order=order,
        title=f"Invoice for order {order.reference}",
        created_by=request.user,
    )
    for line in order.lines.all():
        CommercialLine.objects.create(
            document=inv,
            product=line.product,
            product_variant=line.product_variant,
            description=line.description,
            quantity=Decimal(line.quantity),
            unit_price=line.unit_price,
        )
    inv.recalculate_from_lines()
    inv.save()
    messages.success(request, f"Created {inv.number} from order {order.reference}.")
    return redirect("staff_document_edit", pk=inv.pk)
