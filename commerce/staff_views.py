from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from billing.models import CommercialDocument, CommercialLine, allocate_document_number
from commerce.fulfillment import transition_order
from commerce.fulfillment_forms import OrderStatusForm, ShipmentForm
from commerce.models import CustomerReturn, Order
from commerce.return_forms import CustomerReturnForm
from core.mixins import StaffRequiredMixin
from inventory.models import StockMovement
from inventory.services import change_stock


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
            "lines__product",
            "lines__product_variant",
            "documents",
            "status_events__changed_by",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order_status_choices"] = Order.STATUS_CHOICES
        ctx["status_form"] = OrderStatusForm(initial={"status": self.object.status})
        shipment = getattr(self.object, "shipment", None)
        ctx["shipment_form"] = ShipmentForm(instance=shipment)
        ctx["return_form"] = CustomerReturnForm(order=self.object)
        ctx["customer_returns"] = CustomerReturn.objects.filter(
            order_line__order=self.object
        ).select_related("order_line", "processed_by")
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        note = request.POST.get("staff_note")
        if note is not None:
            self.object.staff_note = note.strip()
        self.object.save(update_fields=["staff_note", "updated_at"])
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


@transaction.atomic
def staff_customer_return(request, pk: int):
    if not request.user.is_staff or request.method != "POST":
        from django.http import Http404

        raise Http404
    order = get_object_or_404(Order, pk=pk)
    form = CustomerReturnForm(request.POST, order=order)
    if not form.is_valid():
        messages.error(request, "; ".join(
            error for errors in form.errors.values() for error in errors
        ))
        return redirect("staff_order_detail", pk=pk)
    returned = form.save(commit=False)
    returned.reference = allocate_document_number("RET")
    returned.processed_by = request.user
    returned.order_line = type(returned.order_line).objects.select_for_update().get(
        pk=returned.order_line_id
    )
    try:
        returned.full_clean()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_order_detail", pk=pk)
    returned.save()
    if returned.disposition == CustomerReturn.DISPOSITION_RESTOCK:
        line = returned.order_line
        change_stock(
            product=line.product,
            product_variant=line.product_variant,
            quantity_delta=returned.quantity,
            movement_type=StockMovement.TYPE_CUSTOMER_RETURN,
            reference=returned.reference,
            note=returned.reason,
            actor=request.user,
        )
    messages.success(request, f"Customer return {returned.reference} recorded.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
def staff_order_transition(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    order = get_object_or_404(Order, pk=pk)
    form = OrderStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid order status.")
        return redirect("staff_order_detail", pk=pk)
    try:
        order = transition_order(
            order,
            form.cleaned_data["status"],
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_order_detail", pk=pk)
    from commerce.notifications import notify_order_status

    notify_order_status(order)
    messages.success(request, f"Order is now {order.get_status_display()}.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
def staff_order_shipment(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    order = get_object_or_404(Order, pk=pk)
    shipment = getattr(order, "shipment", None)
    form = ShipmentForm(request.POST, instance=shipment)
    if not form.is_valid():
        messages.error(request, "Check the shipment details.")
        return redirect("staff_order_detail", pk=pk)
    shipment = form.save(commit=False)
    shipment.order = order
    if shipment.status == shipment.STATUS_IN_TRANSIT and not shipment.dispatched_at:
        shipment.dispatched_at = timezone.now()
    if shipment.status == shipment.STATUS_DELIVERED and not shipment.delivered_at:
        shipment.delivered_at = timezone.now()
    shipment.save()
    target_status = None
    if shipment.status == shipment.STATUS_IN_TRANSIT:
        target_status = Order.STATUS_DISPATCHED
    elif shipment.status == shipment.STATUS_DELIVERED:
        target_status = Order.STATUS_DELIVERED
    if target_status and order.status != target_status:
        try:
            order = transition_order(
                order,
                target_status,
                actor=request.user,
                note=f"Shipment updated: {shipment.get_status_display()}",
            )
        except ValidationError:
            pass
    from commerce.notifications import notify_order_status

    notify_order_status(order)
    messages.success(request, "Shipment details updated.")
    return redirect("staff_order_detail", pk=pk)
