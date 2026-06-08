from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView

from billing.forms import CommercialDocumentForm, CommercialLineForm, PaymentRecordForm


def _line_diff_summary(before: list, after: list) -> str:
    """Produce a short human-readable summary of line changes for AuditEvent."""
    before_by_pk = {b["pk"]: b for b in before if b.get("pk")}
    after_by_pk = {a["pk"]: a for a in after if a.get("pk")}
    parts = []
    for pk, b in before_by_pk.items():
        a = after_by_pk.get(pk)
        if a is None:
            parts.append(f"removed “{b['description'][:40]}”")
            continue
        changes = []
        for key in ("description", "sku", "quantity", "unit_price"):
            if str(b.get(key, "")) != str(a.get(key, "")):
                changes.append(f"{key}: {b.get(key)}→{a.get(key)}")
        if changes:
            parts.append(f"#{pk} ({'; '.join(changes)})")
    for pk, a in after_by_pk.items():
        if pk not in before_by_pk:
            parts.append(f"added “{a['description'][:40]}” × {a['quantity']}")
    if not parts:
        return ""
    summary = "; ".join(parts)
    return summary[:300]

from billing.models import (
    CommercialDocument,
    CommercialLine,
    DocumentPayment,
    allocate_document_number,
)
from billing.pdf import pdf_response
from catalog.models import Product, ProductVariant
from core.audit import log_audit_event
from core.mixins import StaffRequiredMixin
from core.models import CompanySettings

LineFormSet = inlineformset_factory(
    CommercialDocument,
    CommercialLine,
    form=CommercialLineForm,
    extra=1,
    can_delete=True,
)


class CommercialDocumentListView(StaffRequiredMixin, ListView):
    model = CommercialDocument
    template_name = "billing/document_list.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        qs = CommercialDocument.objects.select_related("customer").order_by(
            "-issue_date", "-id"
        )
        t = self.request.GET.get("type")
        if t in dict(CommercialDocument.TYPE_CHOICES):
            qs = qs.filter(doc_type=t)
        st = self.request.GET.get("status")
        if st in dict(CommercialDocument.STATUS_CHOICES):
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["document_status_choices"] = CommercialDocument.STATUS_CHOICES
        return ctx


class CommercialDocumentCreateView(StaffRequiredMixin, CreateView):
    model = CommercialDocument
    form_class = CommercialDocumentForm
    template_name = "billing/document_create.html"

    def form_valid(self, form):
        company = CompanySettings.load()
        with transaction.atomic():
            doc = form.save(commit=False)
            prefix = CommercialDocument.PREFIX[doc.doc_type]
            doc.number = allocate_document_number(prefix)
            doc.created_by = self.request.user
            if doc.tax_rate is None:
                doc.tax_rate = company.default_tax_rate
            doc.save()
        log_audit_event(
            actor=self.request.user,
            verb="billing.document_created",
            summary=f"{doc.number} ({doc.get_doc_type_display()}) customer {doc.customer_id}",
            target=doc,
        )
        messages.success(
            self.request,
            f"Created {doc.number}. Add line items and save when ready.",
        )
        return redirect("staff_document_edit", pk=doc.pk)


class CommercialDocumentUpdateView(StaffRequiredMixin, UpdateView):
    model = CommercialDocument
    form_class = CommercialDocumentForm
    template_name = "billing/document_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["line_formset"] = LineFormSet(
            self.request.POST if self.request.method == "POST" else None,
            instance=self.object,
        )
        ctx["is_create"] = False
        variants_meta = [
            {
                "id": v.pk,
                "pid": v.product_id,
                "label": f"{v.product.name} — {v.name}",
                "price": str(v.price),
            }
            for v in ProductVariant.objects.filter(is_active=True).select_related("product")
        ]
        ctx["variants_for_js"] = variants_meta
        ctx["products_price_map"] = {
            str(p.pk): str(p.price) for p in Product.objects.filter(is_published=True)
        }
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data(form=form)
        fs = ctx["line_formset"]
        if not fs.is_valid():
            return self.render_to_response(ctx)
        previous_lines = []
        if self.object and self.object.pk:
            previous_lines = [
                {
                    "pk": line.pk,
                    "description": line.description,
                    "sku": line.sku,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                }
                for line in self.object.lines.all()
            ]
        with transaction.atomic():
            self.object = form.save()
            fs.instance = self.object
            fs.save()
            self.object.recalculate_from_lines()
            self.object.sync_payment_status()
            self.object.save(
                update_fields=[
                    "subtotal",
                    "tax_amount",
                    "total",
                    "status",
                    "updated_at",
                ]
            )
        new_lines = [
            {
                "pk": line.pk,
                "description": line.description,
                "sku": line.sku,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
            }
            for line in self.object.lines.all()
        ]
        diff_summary = _line_diff_summary(previous_lines, new_lines)
        summary = f"{self.object.number} total={self.object.total} status={self.object.status}"
        if diff_summary:
            summary = f"{summary} | lines: {diff_summary}"
        log_audit_event(
            actor=self.request.user,
            verb="billing.document_saved",
            summary=summary[:500],
            target=self.object,
        )
        messages.success(self.request, "Document saved.")
        return redirect("staff_document_edit", pk=self.object.pk)


class CommercialDocumentDetailView(StaffRequiredMixin, DetailView):
    model = CommercialDocument
    template_name = "billing/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        return CommercialDocument.objects.select_related("customer").prefetch_related(
            "lines__product",
            "lines__product_variant",
            "payments__recorded_by",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        doc = self.object
        show_pay = doc.doc_type in (
            CommercialDocument.TYPE_INVOICE,
            CommercialDocument.TYPE_PROFORMA,
        ) and doc.status != CommercialDocument.STATUS_CANCELLED
        ctx["show_payment_form"] = show_pay and doc.balance_due > 0
        ctx["payment_form"] = PaymentRecordForm()
        ctx["payment_history"] = doc.payments.all()
        ctx["quote_approval_pending"] = (
            doc.doc_type == CommercialDocument.TYPE_QUOTE
            and doc.quote_requires_internal_approval
            and not doc.quote_internally_approved
        )
        ctx["quote_approval_complete"] = (
            doc.doc_type == CommercialDocument.TYPE_QUOTE
            and doc.quote_requires_internal_approval
            and doc.quote_internally_approved
        )
        if doc.doc_type == CommercialDocument.TYPE_QUOTE and doc.quote_customer_token:
            ctx["quote_customer_url"] = request.build_absolute_uri(
                reverse("quote_customer_portal", kwargs={"token": doc.quote_customer_token})
            )
        ctx["quote_customer_pending"] = doc.customer_quote_pending
        ctx["quote_customer_accepted"] = doc.quote_customer_accepted is True
        ctx["quote_customer_declined"] = doc.quote_customer_accepted is False
        return ctx


@transaction.atomic
def document_record_payment(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(CommercialDocument, pk=pk)
    if doc.status == CommercialDocument.STATUS_CANCELLED:
        messages.error(request, "Cannot record payments on a cancelled document.")
        return redirect("staff_document_view", pk=pk)
    if doc.doc_type not in (
        CommercialDocument.TYPE_INVOICE,
        CommercialDocument.TYPE_PROFORMA,
    ):
        messages.error(request, "Payments apply to invoices and proformas only.")
        return redirect("staff_document_view", pk=pk)
    if request.method != "POST":
        return redirect("staff_document_view", pk=pk)
    form = PaymentRecordForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check the payment form and try again.")
        return redirect("staff_document_view", pk=pk)
    amount = form.cleaned_data["amount"]
    if amount <= 0:
        messages.error(request, "Amount must be positive.")
        return redirect("staff_document_view", pk=pk)
    remaining = doc.balance_due
    if amount > remaining:
        messages.error(
            request,
            f"Amount exceeds balance due ({remaining}).",
        )
        return redirect("staff_document_view", pk=pk)
    DocumentPayment.objects.create(
        document=doc,
        amount=amount,
        method=form.cleaned_data["method"],
        reference=form.cleaned_data.get("reference") or "",
        note=form.cleaned_data.get("note") or "",
        recorded_by=request.user,
    )
    doc.amount_paid = (doc.amount_paid + amount).quantize(Decimal("0.01"))
    if doc.status == CommercialDocument.STATUS_DRAFT:
        doc.status = CommercialDocument.STATUS_ISSUED
    doc.sync_payment_status()
    doc.save(
        update_fields=["amount_paid", "status", "updated_at"]
    )
    log_audit_event(
        actor=request.user,
        verb="billing.payment_recorded",
        summary=f"{doc.number}: +{amount} ({doc.get_status_display()}) balance {doc.balance_due}",
        target=doc,
    )
    messages.success(request, f"Recorded payment of {amount}.")
    return redirect("staff_document_view", pk=pk)


def document_pdf_view(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(
        CommercialDocument.objects.prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    return pdf_response(doc, inline=True)


def convert_document(request, pk: int, target: str):
    if not request.user.is_staff:
        raise Http404
    source = get_object_or_404(
        CommercialDocument.objects.prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    mapping = {
        "proforma": CommercialDocument.TYPE_PROFORMA,
        "invoice": CommercialDocument.TYPE_INVOICE,
        "delivery-note": CommercialDocument.TYPE_DELIVERY_NOTE,
        "demand-note": CommercialDocument.TYPE_DEMAND_NOTE,
        "receipt": CommercialDocument.TYPE_RECEIPT,
    }
    if target not in mapping:
        raise Http404
    new_type = mapping[target]

    if source.doc_type == CommercialDocument.TYPE_QUOTE:
        if source.quote_requires_internal_approval and not source.quote_internally_approved:
            if new_type in (
                CommercialDocument.TYPE_PROFORMA,
                CommercialDocument.TYPE_INVOICE,
            ):
                messages.error(
                    request,
                    "This quotation requires internal approval before it can be converted.",
                )
                return redirect("staff_document_edit", pk=source.pk)
        if (
            source.quote_requires_customer_acceptance
            and source.quote_customer_accepted is not True
            and new_type
            in (CommercialDocument.TYPE_PROFORMA, CommercialDocument.TYPE_INVOICE)
        ):
            messages.error(
                request,
                "The customer must accept this quotation before it can be converted.",
            )
            return redirect("staff_document_edit", pk=source.pk)

    if source.doc_type == CommercialDocument.TYPE_RECEIPT:
        messages.error(request, "Receipts cannot be converted.")
        return redirect("staff_document_edit", pk=source.pk)

    if (
        new_type == CommercialDocument.TYPE_PROFORMA
        and source.doc_type != CommercialDocument.TYPE_QUOTE
    ):
        messages.error(request, "Only quotations can be converted into proformas.")
        return redirect("staff_document_edit", pk=source.pk)

    if new_type == CommercialDocument.TYPE_INVOICE and source.doc_type not in (
        CommercialDocument.TYPE_QUOTE,
        CommercialDocument.TYPE_PROFORMA,
    ):
        messages.error(request, "Invalid source document for an invoice.")
        return redirect("staff_document_edit", pk=source.pk)

    if new_type == CommercialDocument.TYPE_DELIVERY_NOTE and source.order is None:
        messages.error(request, "Delivery notes require an order link.")
        return redirect("staff_document_edit", pk=source.pk)

    if new_type == CommercialDocument.TYPE_DEMAND_NOTE and source.doc_type != (
        CommercialDocument.TYPE_INVOICE
    ):
        messages.error(request, "Demand notes can be created from invoices only.")
        return redirect("staff_document_edit", pk=source.pk)

    if new_type == CommercialDocument.TYPE_RECEIPT and source.doc_type not in (
        CommercialDocument.TYPE_INVOICE,
        CommercialDocument.TYPE_PROFORMA,
    ):
        messages.error(request, "Receipts can be created from invoices/proformas only.")
        return redirect("staff_document_edit", pk=source.pk)

    prefix = CommercialDocument.PREFIX[new_type]
    with transaction.atomic():
        # Receipts: copy payment totals + history only (no commercial lines needed).
        if new_type == CommercialDocument.TYPE_RECEIPT:
            rec = CommercialDocument.objects.create(
                doc_type=new_type,
                number=allocate_document_number(prefix),
                customer=source.customer,
                status=CommercialDocument.STATUS_ISSUED,
                title=f"Receipt for {source.number}",
                issue_date=source.issue_date,
                due_date=None,
                notes=source.notes,
                terms=source.terms,
                tax_rate=source.tax_rate,
                subtotal=0,
                tax_amount=0,
                total=source.amount_paid,
                amount_paid=source.amount_paid,
                order=source.order,
                source_document=source,
                created_by=request.user,
            )
            for p in source.payments.all():
                DocumentPayment.objects.create(
                    document=rec,
                    amount=p.amount,
                    method=p.method,
                    reference=p.reference,
                    note=p.note,
                    recorded_by=p.recorded_by,
                )
            messages.success(request, f"Created {rec.number} from {source.number}.")
            log_audit_event(
                actor=request.user,
                verb="billing.document_converted",
                summary=f"{source.number} → {rec.number} (receipt)",
                target=rec,
            )
            return redirect("staff_document_view", pk=rec.pk)

        new_doc = CommercialDocument.objects.create(
            doc_type=new_type,
            number=allocate_document_number(prefix),
            customer=source.customer,
            status=CommercialDocument.STATUS_DRAFT,
            title=(
                f"Delivery note for {source.order.reference}"
                if new_type == CommercialDocument.TYPE_DELIVERY_NOTE and source.order
                else (f"Demand note for {source.number}" if new_type == CommercialDocument.TYPE_DEMAND_NOTE else source.title)
            ),
            issue_date=source.issue_date,
            due_date=source.due_date,
            notes=source.notes,
            terms=source.terms,
            tax_rate=source.tax_rate,
            subtotal=0,
            tax_amount=0,
            total=0,
            order=source.order,
            source_document=source,
            created_by=request.user,
        )
        for line in source.lines.all():
            CommercialLine.objects.create(
                document=new_doc,
                product=line.product,
                product_variant=line.product_variant,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        new_doc.recalculate_from_lines()
        new_doc.save()
    log_audit_event(
        actor=request.user,
        verb="billing.document_converted",
        summary=f"{source.number} → {new_doc.number} ({new_doc.get_doc_type_display()})",
        target=new_doc,
    )
    messages.success(request, f"Created {new_doc.number} from {source.number}.")
    return redirect("staff_document_edit", pk=new_doc.pk)


@require_POST
def quote_internal_approve(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(CommercialDocument, pk=pk)
    if doc.doc_type != CommercialDocument.TYPE_QUOTE:
        messages.error(request, "Only quotations can be approved this way.")
        return redirect("staff_document_view", pk=pk)
    if not doc.quote_requires_internal_approval:
        messages.info(request, "This quotation does not require internal approval.")
        return redirect("staff_document_view", pk=pk)
    if doc.quote_internally_approved:
        messages.info(request, "This quotation is already approved.")
        return redirect("staff_document_view", pk=pk)
    doc.quote_internally_approved = True
    doc.quote_approved_by = request.user
    doc.quote_approved_at = timezone.now()
    doc.save(
        update_fields=[
            "quote_internally_approved",
            "quote_approved_by",
            "quote_approved_at",
            "updated_at",
        ]
    )
    log_audit_event(
        actor=request.user,
        verb="billing.quote_internally_approved",
        summary=f"Quote {doc.number} approved for conversion",
        target=doc,
    )
    messages.success(request, f"Approved quotation {doc.number} for conversion.")
    return redirect("staff_document_view", pk=pk)


@require_POST
def quote_enable_customer_acceptance(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(CommercialDocument, pk=pk)
    if doc.doc_type != CommercialDocument.TYPE_QUOTE:
        messages.error(request, "Only quotations support customer acceptance.")
        return redirect("staff_document_view", pk=pk)
    doc.quote_requires_customer_acceptance = True
    doc.ensure_customer_quote_token()
    if doc.quote_customer_accepted is False:
        doc.quote_customer_accepted = None
    doc.save(
        update_fields=[
            "quote_requires_customer_acceptance",
            "quote_customer_token",
            "quote_customer_accepted",
            "updated_at",
        ]
    )
    url = request.build_absolute_uri(
        reverse("quote_customer_portal", kwargs={"token": doc.quote_customer_token})
    )
    messages.success(request, f"Customer approval link ready. Share: {url}")
    return redirect("staff_document_view", pk=pk)


def quote_customer_portal(request, token):
    doc = get_object_or_404(
        CommercialDocument.objects.select_related("customer").prefetch_related("lines"),
        quote_customer_token=token,
        doc_type=CommercialDocument.TYPE_QUOTE,
    )
    company = CompanySettings.load()
    if request.method == "POST" and doc.quote_customer_accepted is None:
        action = request.POST.get("action")
        name = (request.POST.get("signature_name") or "").strip()
        if action == "accept" and name:
            doc.quote_customer_accepted = True
            doc.quote_customer_signature_name = name[:200]
            doc.quote_customer_responded_at = timezone.now()
            doc.save(
                update_fields=[
                    "quote_customer_accepted",
                    "quote_customer_signature_name",
                    "quote_customer_responded_at",
                    "updated_at",
                ]
            )
            log_audit_event(
                actor=request.user if request.user.is_authenticated else None,
                verb="billing.quote_customer_accepted",
                summary=f"Quote {doc.number} accepted by {name}",
                target=doc,
            )
            messages.success(request, "Thank you — quotation accepted.")
            return redirect("quote_customer_portal", token=token)
        if action == "decline":
            doc.quote_customer_accepted = False
            doc.quote_customer_decline_reason = (
                (request.POST.get("decline_reason") or "").strip()[:500]
            )
            doc.quote_customer_responded_at = timezone.now()
            doc.save(
                update_fields=[
                    "quote_customer_accepted",
                    "quote_customer_decline_reason",
                    "quote_customer_responded_at",
                    "updated_at",
                ]
            )
            log_audit_event(
                actor=request.user if request.user.is_authenticated else None,
                verb="billing.quote_customer_declined",
                summary=f"Quote {doc.number} declined",
                target=doc,
            )
            messages.info(request, "Quotation declined. Our team will follow up.")
            return redirect("quote_customer_portal", token=token)
        messages.error(request, "Enter your full name to accept, or use Decline.")
    return render(
        request,
        "billing/quote_customer.html",
        {"document": doc, "company": company},
    )
