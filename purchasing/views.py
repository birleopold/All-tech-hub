from django.contrib import messages
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, UpdateView

from core.mixins import StaffRequiredMixin
from purchasing.models import PurchaseLine, PurchaseOrder, StockReceipt, StockReceiptLine


PurchaseLineFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseLine,
    fields=("product", "product_variant", "description", "quantity", "unit_cost"),
    extra=1,
    can_delete=True,
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
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data(form=form)
        fs = ctx["lines_formset"]
        if not fs.is_valid():
            return self.render_to_response(ctx)
        with transaction.atomic():
            self.object = form.save()
            fs.instance = self.object
            fs.save()
        messages.success(self.request, "Purchase order saved.")
        return redirect("staff_po_edit", pk=self.object.pk)


@transaction.atomic
def receive_stock(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    po = get_object_or_404(
        PurchaseOrder.objects.prefetch_related("lines__product", "lines__product_variant"),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("staff_po_edit", pk=pk)
    # Create one receipt and receive the remaining quantities by default.
    receipt = StockReceipt.objects.create(purchase_order=po, received_by=request.user)
    received_any = False
    for line in po.lines.all():
        remaining = int(line.quantity) - int(line.received_quantity)
        if remaining <= 0:
            continue
        rline = StockReceiptLine.objects.create(
            receipt=receipt,
            purchase_line=line,
            quantity_received=remaining,
        )
        rline.apply()
        received_any = True
    po.refresh_from_db()
    po.sync_receiving_status()
    po.save(update_fields=["status", "updated_at"])
    if not received_any:
        messages.info(request, "Nothing to receive (all lines already received).")
        return redirect("staff_po_edit", pk=pk)
    messages.success(request, f"Stock received: {receipt.number}. Inventory updated.")
    return redirect("staff_po_edit", pk=pk)
