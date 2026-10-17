from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, UpdateView

from billing.models import allocate_document_number
from core.mixins import StaffRequiredMixin
from inventory.models import StockMovement
from inventory.services import change_stock
from purchasing.forms import SupplierReturnForm
from purchasing.models import (
    PurchaseLine,
    PurchaseOrder,
    StockReceipt,
    StockReceiptLine,
    SupplierReturn,
)

class SafePurchaseLineFormSet(BaseInlineFormSet):
    """Received goods keep their original identity, price and receipt trail."""

    def add_fields(self, form, index):
        super().add_fields(form, index)
        if form.instance.pk and form.instance.received_quantity:
            for name in ("product", "product_variant", "unit_cost", "DELETE"):
                if name in form.fields:
                    form.fields[name].disabled = True

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            data = getattr(form, "cleaned_data", None)
            if not data or not form.instance.pk:
                continue
            before = PurchaseLine.objects.filter(pk=form.instance.pk).values(
                "product_id", "product_variant_id", "unit_cost",
                "received_quantity",
            ).first()
            if not before or not before["received_quantity"]:
                continue
            if data.get("DELETE"):
                form.add_error(
                    None, "Received purchase lines cannot be removed."
                )
                continue
            for field in ("product", "product_variant"):
                selected = data.get(field)
                if (selected.pk if selected else None) != before[field + "_id"]:
                    form.add_error(
                        field, "Cannot change an item after goods were received."
                    )
            if data.get("unit_cost") != before["unit_cost"]:
                form.add_error(
                    "unit_cost", "Received goods keep their original unit cost."
                )
            quantity = data.get("quantity")
            if quantity is not None and quantity < before["received_quantity"]:
                form.add_error(
                    "quantity", "Ordered quantity cannot be below goods received."
                )


PurchaseLineFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseLine,
    fields=("product", "product_variant", "description", "quantity", "unit_cost"),
    extra=1,
    can_delete=True,
    formset=SafePurchaseLineFormSet,
)


class PurchasingHomeView(StaffRequiredMixin, TemplateView):
    template_name = "purchasing/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recent_pos"] = PurchaseOrder.objects.select_related("supplier").order_by("-ordered_on", "-id")[:10]
        return ctx


class PurchaseOrderCreateView(StaffRequiredMixin, CreateView):
    model = PurchaseOrder
    fields = ("supplier", "status", "ordered_on", "expected_on", "notes")
    template_name = "purchasing/po_create.html"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.save()
        messages.success(self.request, f"Created PO {obj.number}. Add line items.")
        return redirect("staff_po_edit", pk=obj.pk)


class PurchaseOrderUpdateView(StaffRequiredMixin, UpdateView):
    model = PurchaseOrder
    fields = ("supplier", "status", "ordered_on", "expected_on", "notes")
    template_name = "purchasing/po_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lines_formset"] = PurchaseLineFormSet(
            self.request.POST if self.request.method == "POST" else None,
            instance=self.object,
        )
        ctx["supplier_return_form"] = SupplierReturnForm(
            purchase_order=self.object
        )
        ctx["supplier_returns"] = SupplierReturn.objects.filter(
            purchase_line__purchase_order=self.object
        ).select_related("purchase_line", "processed_by")
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            self.object = PurchaseOrder.objects.select_for_update().get(
                pk=self.object.pk
            )
            ctx = self.get_context_data(form=form)
            fs = ctx["lines_formset"]
            if self.object.lines.filter(received_quantity__gt=0).exists():
                if form.cleaned_data["supplier"].pk != self.object.supplier_id:
                    form.add_error(
                        "supplier",
                        "Cannot change the supplier after stock has been received.",
                    )
            if not fs.is_valid() or form.errors:
                return self.render_to_response(ctx)
            # Keep the already validated/bound form instance; replacing it
            # with a freshly locked object would discard submitted values.
            self.object = form.save()
            fs.instance = self.object
            fs.save()
            # Never trust manually chosen 'received' or 'partial' labels
            # over actual goods receipts.
            if self.object.status != PurchaseOrder.STATUS_CANCELLED:
                self.object.sync_receiving_status()
                if self.object.status in (
                    PurchaseOrder.STATUS_PARTIAL,
                    PurchaseOrder.STATUS_RECEIVED,
                ) and not self.object.lines.filter(
                    received_quantity__gt=0
                ).exists():
                    self.object.status = PurchaseOrder.STATUS_SENT
                self.object.save(update_fields=["status", "updated_at"])
        messages.success(self.request, "Purchase order saved.")
        return redirect("staff_po_edit", pk=self.object.pk)


@transaction.atomic
def receive_stock(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    po = get_object_or_404(
        PurchaseOrder.objects.select_for_update().prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("staff_po_edit", pk=pk)
    if po.status == PurchaseOrder.STATUS_CANCELLED:
        messages.error(request, "Cancelled purchase orders cannot receive stock.")
        return redirect("staff_po_edit", pk=pk)
    remaining_lines = [
        (line, line.remaining_quantity)
        for line in po.lines.all()
        if line.remaining_quantity
    ]
    if not remaining_lines:
        messages.info(request, "Nothing to receive (all lines already received).")
        return redirect("staff_po_edit", pk=pk)
    quantities_supplied = any(key.startswith("quantity_") for key in request.POST)
    requested_lines = []
    for line, remaining in remaining_lines:
        if quantities_supplied:
            raw_quantity = request.POST.get(f"quantity_{line.pk}", "0").strip()
            try:
                quantity = int(raw_quantity or 0)
            except (TypeError, ValueError):
                messages.error(request, "Received quantities must be whole numbers.")
                return redirect("staff_po_edit", pk=pk)
            if quantity < 0 or quantity > remaining:
                messages.error(
                    request,
                    f"Receive between 0 and {remaining} units of {line.product.name}.",
                )
                return redirect("staff_po_edit", pk=pk)
        else:
            quantity = remaining
        if quantity:
            requested_lines.append((line, quantity))
    if not requested_lines:
        messages.error(request, "Enter a quantity for at least one purchase line.")
        return redirect("staff_po_edit", pk=pk)
    receipt = StockReceipt.objects.create(purchase_order=po, received_by=request.user)
    for line, quantity in requested_lines:
        rline = StockReceiptLine.objects.create(
            receipt=receipt,
            purchase_line=line,
            quantity_received=quantity,
        )
        rline.apply()
    po.refresh_from_db()
    po.sync_receiving_status()
    po.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Stock received: {receipt.number}. Inventory updated.")
    return redirect("staff_po_edit", pk=pk)


@transaction.atomic
def supplier_return(request, pk: int):
    if not request.user.is_staff or request.method != "POST":
        raise Http404
    po = get_object_or_404(PurchaseOrder, pk=pk)
    form = SupplierReturnForm(request.POST, purchase_order=po)
    if not form.is_valid():
        messages.error(request, "Check the supplier return details.")
        return redirect("staff_po_edit", pk=pk)
    returned = form.save(commit=False)
    returned.reference = allocate_document_number("SRT")
    returned.processed_by = request.user
    returned.purchase_line = PurchaseLine.objects.select_for_update().get(
        pk=returned.purchase_line_id
    )
    try:
        returned.full_clean()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_po_edit", pk=pk)
    line = returned.purchase_line
    try:
        change_stock(
            product=line.product,
            product_variant=line.product_variant,
            quantity_delta=-returned.quantity,
            movement_type=StockMovement.TYPE_SUPPLIER_RETURN,
            reference=returned.reference,
            note=returned.reason,
            actor=request.user,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_po_edit", pk=pk)
    returned.save()
    messages.success(request, f"Supplier return {returned.reference} recorded.")
    return redirect("staff_po_edit", pk=pk)
