from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView

from billing.forms import (
    AccountPaymentForm,
    CommercialDocumentForm,
    CommercialLineForm,
    DocumentActionForm,
    PaymentRecordForm,
    PaymentRefundForm,
    RequiredCommercialLineFormSet,
)
from billing.models import (
    AccountPayment,
    CommercialDocument,
    CommercialLine,
    CustomerCredit,
    DocumentPayment,
    PaymentSubmission,
    DocumentRevision,
    DocumentTemplate,
    PaymentAllocation,
    allocate_document_number,
)
from billing.pdf import pdf_response
from billing.payment_submissions import (
    reject_payment_submission,
    submit_payment_confirmation,
    verify_payment_submission,
)
from catalog.models import Product, ProductVariant
from core.audit import log_audit_event
from core.mixins import StaffRequiredMixin
from core.models import CompanySettings, ContactMessage
from crm.models import Customer
from inventory.models import StockMovement
from inventory.services import change_stock, current_stock


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
        for key in ("description", "quantity", "unit_price"):
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


def _create_revision(document, actor, reason: str) -> DocumentRevision:
    next_number = document.revision_number + 1
    revision = DocumentRevision.objects.create(
        document=document,
        revision_number=next_number,
        reason=reason[:255],
        snapshot=document.snapshot_data(),
        created_by=actor,
    )
    document.revision_number = next_number
    document.save(update_fields=["revision_number", "updated_at"])
    return revision


def _save_walk_in_customer(form, document):
    if not form.cleaned_data.get("save_customer_to_crm") or document.customer_id:
        return
    customer = Customer.objects.create(
        name=document.customer_name,
        company_name=document.customer_company,
        email=document.customer_email or f"walkin-{document.pk}@invalid.local",
        phone=document.customer_phone,
        tax_reference=document.customer_tax_reference,
        notes=f"Created from commercial document {document.number}.",
    )
    document.customer = customer
    document.save(update_fields=["customer", "updated_at"])


def _save_document_template(form, document, actor):
    name = (form.cleaned_data.get("template_name") or "").strip()
    if form.data.get("save_action") != "template" or not name:
        return None
    template, _ = DocumentTemplate.objects.update_or_create(
        name=name,
        defaults={
            "doc_type": document.doc_type,
            "title": document.title,
            "notes": document.notes,
            "terms": document.terms,
            "pricing_mode": document.pricing_mode,
            "tax_rate": document.tax_rate,
            "lines": [
                {
                    key: value
                    for key, value in line.snapshot_data().items()
                    if key not in {"total"}
                }
                for line in document.lines.all()
            ],
            "created_by": actor,
            "is_active": True,
        },
    )
    return template


def _post_inventory_for_document(document, actor):
    if document.inventory_posted_at or document.order_id:
        return
    if document.doc_type not in (
        CommercialDocument.TYPE_INVOICE,
        CommercialDocument.TYPE_DELIVERY_NOTE,
        CommercialDocument.TYPE_RECEIPT,
    ):
        return
    stock_lines = []
    for line in document.lines.select_related("product", "product_variant"):
        if (
            line.source_type != CommercialLine.SOURCE_STOCK
            or not line.product_id
            or not line.product.track_inventory
        ):
            continue
        quantity = int(line.quantity)
        if Decimal(quantity) != line.quantity:
            raise ValidationError(
                f"{line.description}: inventory items require whole-number quantities."
            )
        available = current_stock(
            product=line.product, product_variant=line.product_variant
        )
        if available < quantity:
            raise ValidationError(
                f"{line.description}: only {available} unit(s) are available."
            )
        stock_lines.append((line, quantity))
    for line, quantity in stock_lines:
        change_stock(
            product=line.product,
            product_variant=line.product_variant,
            quantity_delta=-quantity,
            movement_type=StockMovement.TYPE_SALE,
            reference=document.number,
            note=f"Issued on {document.get_doc_type_display()}",
            actor=actor,
        )
    document.inventory_posted_at = timezone.now()
    document.save(update_fields=["inventory_posted_at", "updated_at"])


def _issue_document(document, actor, reason="Initial issue"):
    if document.status == CommercialDocument.STATUS_CANCELLED:
        raise ValidationError("Cancelled documents cannot be issued.")
    _post_inventory_for_document(document, actor)
    if not document.revisions.exists():
        _create_revision(document, actor, reason)
    document.status = CommercialDocument.STATUS_ISSUED
    document.lock(actor)
    document.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])


def _commercial_warnings(document):
    warnings = []
    duplicate_qs = CommercialDocument.objects.filter(
        doc_type=document.doc_type,
        customer_name__iexact=document.customer_name,
        issue_date=document.issue_date,
        total=document.total,
    ).exclude(pk=document.pk)
    if duplicate_qs.exists():
        warnings.append("A similar same-day document already exists for this customer.")
    for line in document.lines.select_related("product", "product_variant"):
        expected = (
            line.product_variant.price
            if line.product_variant_id
            else (line.product.price if line.product_id else None)
        )
        if expected and expected > 0:
            difference = abs(line.unit_price - expected) / expected
            if difference >= Decimal("0.30"):
                warnings.append(
                    f"“{line.description}” differs from its catalog price by at least 30%."
                )
    return warnings[:5]


def _record_receipt_payment(document, actor):
    if (
        document.doc_type != CommercialDocument.TYPE_RECEIPT
        or not document.receipt_payment_method
        or document.amount_tendered <= 0
        or document.payments.exists()
    ):
        return
    applied = min(document.amount_tendered, max(document.total, Decimal("0")))
    if applied <= 0:
        return
    DocumentPayment.objects.create(
        document=document,
        amount=applied,
        method=document.receipt_payment_method,
        reference=document.receipt_payment_reference,
        note="Recorded during receipt creation",
        recorded_by=actor,
    )
    document.amount_paid = applied
    if applied >= document.total:
        document.status = CommercialDocument.STATUS_PAID
    document.save(update_fields=["amount_paid", "status", "updated_at"])

LineFormSet = inlineformset_factory(
    CommercialDocument,
    CommercialLine,
    form=CommercialLineForm,
    formset=RequiredCommercialLineFormSet,
    extra=2,
    can_delete=True,
)


class CommercialDocumentEditorMixin:
    def get_line_formset(self):
        return LineFormSet(
            self.request.POST if self.request.method == "POST" else None,
            instance=self.object,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("line_formset", self.get_line_formset())
        ctx["is_create"] = self.object is None or self.object.pk is None
        variants_meta = [
            {
                "id": variant.pk,
                "pid": variant.product_id,
                "label": f"{variant.product.name} — {variant.name}",
                "price": str(variant.price),
            }
            for variant in ProductVariant.objects.filter(is_active=True).select_related(
                "product"
            )
        ]
        products = Product.objects.filter(is_published=True)
        ctx["variants_for_js"] = variants_meta
        ctx["products_price_map"] = {
            str(product.pk): str(product.price) for product in products
        }
        ctx["products_name_map"] = {
            str(product.pk): product.name for product in products
        }
        ctx["products_source_map"] = {
            str(product.pk): (
                CommercialLine.SOURCE_SERVICE
                if product.kind == Product.KIND_SERVICE
                else CommercialLine.SOURCE_STOCK
            )
            for product in products
        }
        ctx["customers_for_js"] = [
            {
                "id": customer.pk,
                "name": customer.name,
                "company": customer.company_name,
                "email": customer.email,
                "phone": customer.phone,
                "tax_reference": customer.tax_reference,
            }
            for customer in Customer.objects.all()
        ]
        ctx["templates_for_js"] = [
            {
                "id": template.pk,
                "doc_type": template.doc_type,
                "title": template.title,
                "notes": template.notes,
                "terms": template.terms,
                "pricing_mode": template.pricing_mode,
                "tax_rate": str(template.tax_rate),
                "lines": template.lines,
            }
            for template in DocumentTemplate.objects.filter(is_active=True)
        ]
        ctx["can_view_margin"] = self.request.user.has_perm(
            "billing.view_document_margin"
        )
        ctx["can_revise"] = self.request.user.has_perm(
            "billing.revise_issued_document"
        )
        ctx["can_void"] = self.request.user.has_perm(
            "billing.void_commercial_document"
        )
        return ctx

    def get_initial(self):
        initial = super().get_initial()
        if getattr(self, "object", None) is None:
            initial.setdefault("salesperson", self.request.user)
        return initial


class CommercialDocumentListView(StaffRequiredMixin, ListView):
    model = CommercialDocument
    template_name = "billing/document_list.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_QUOTE,
            due_date__lt=timezone.localdate(),
            status__in=[
                CommercialDocument.STATUS_DRAFT,
                CommercialDocument.STATUS_ISSUED,
            ],
        ).update(status=CommercialDocument.STATUS_EXPIRED)
        qs = CommercialDocument.objects.select_related("customer").order_by(
            "-issue_date", "-id"
        )
        t = self.request.GET.get("type")
        if t in dict(CommercialDocument.TYPE_CHOICES):
            qs = qs.filter(doc_type=t)
        st = self.request.GET.get("status")
        if st in dict(CommercialDocument.STATUS_CHOICES):
            qs = qs.filter(status=st)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(number__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer_company__icontains=q)
                | Q(title__icontains=q)
                | Q(contact_reference__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["document_status_choices"] = CommercialDocument.STATUS_CHOICES
        ctx["document_type_choices"] = CommercialDocument.TYPE_CHOICES
        return ctx


class CommercialDocumentCreateView(
    StaffRequiredMixin, CommercialDocumentEditorMixin, CreateView
):
    model = CommercialDocument
    form_class = CommercialDocumentForm
    template_name = "billing/document_form.html"

    def form_valid(self, form):
        discount_value = form.cleaned_data.get("discount_value") or Decimal("0")
        maximum_discount = CompanySettings.load().maximum_unapproved_discount_percent
        if (
            form.cleaned_data.get("discount_type")
            == CommercialDocument.DISCOUNT_PERCENT
            and discount_value > maximum_discount
            and not self.request.user.has_perm("billing.override_document_discount")
        ):
            form.add_error(
                "discount_value",
                f"Discounts above {maximum_discount}% require the discount override permission.",
            )
            return self.form_invalid(form)
        line_formset = self.get_line_formset()
        if not line_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, line_formset=line_formset)
            )
        company = CompanySettings.load()
        with transaction.atomic():
            doc = form.save(commit=False)
            prefix = CommercialDocument.PREFIX[doc.doc_type]
            doc.number = allocate_document_number(prefix)
            doc.created_by = self.request.user
            if doc.tax_rate is None:
                doc.tax_rate = company.default_tax_rate
            doc.save()
            line_formset.instance = doc
            line_formset.save()
            doc.recalculate_from_lines()
            if doc.doc_type in (
                CommercialDocument.TYPE_INVOICE,
                CommercialDocument.TYPE_PROFORMA,
            ):
                doc.sync_payment_status()
            doc.save(
                update_fields=[
                    "subtotal",
                    "line_discount_amount",
                    "discount_amount",
                    "tax_amount",
                    "withholding_tax_amount",
                    "total",
                    "change_due",
                    "status",
                    "updated_at",
                ]
            )
            _save_walk_in_customer(form, doc)
            approval_threshold = company.document_approval_threshold
            approval_required = (
                doc.status in (
                    CommercialDocument.STATUS_ISSUED,
                    CommercialDocument.STATUS_PAID,
                )
                and approval_threshold > 0
                and doc.total > approval_threshold
                and not self.request.user.has_perm(
                    "billing.approve_high_value_document"
                )
            )
            if approval_required:
                doc.status = CommercialDocument.STATUS_DRAFT
                doc.save(update_fields=["status", "updated_at"])
            if doc.status in (
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PAID,
            ):
                requested_status = doc.status
                try:
                    _issue_document(doc, self.request.user)
                except ValidationError as exc:
                    doc.status = CommercialDocument.STATUS_DRAFT
                    doc.save(update_fields=["status", "updated_at"])
                    messages.warning(
                        self.request,
                        "Saved as draft: " + "; ".join(exc.messages),
                    )
                else:
                    if requested_status == CommercialDocument.STATUS_PAID:
                        doc.status = requested_status
                        doc.save(update_fields=["status", "updated_at"])
            _record_receipt_payment(doc, self.request.user)
            saved_template = _save_document_template(form, doc, self.request.user)
        self.object = doc
        log_audit_event(
            actor=self.request.user,
            verb="billing.document_created",
            summary=f"{doc.number} ({doc.get_doc_type_display()}) customer {doc.display_customer_name}",
            target=doc,
        )
        messages.success(
            self.request,
            f"Created {doc.number}."
            + (f" Saved template “{saved_template.name}”." if saved_template else ""),
        )
        if approval_required:
            messages.warning(
                self.request,
                f"Saved as draft because totals above {company.currency_code} "
                f"{approval_threshold} require high-value approval.",
            )
        for warning in _commercial_warnings(doc):
            messages.warning(self.request, warning)
        if self.request.POST.get("save_action") == "view":
            return redirect("staff_document_view", pk=doc.pk)
        return redirect("staff_document_edit", pk=doc.pk)


class CommercialDocumentUpdateView(
    StaffRequiredMixin, CommercialDocumentEditorMixin, UpdateView
):
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
        ctx["products_name_map"] = {
            str(p.pk): p.name for p in Product.objects.filter(is_published=True)
        }
        ctx["products_source_map"] = {
            str(p.pk): (
                CommercialLine.SOURCE_SERVICE
                if p.kind == Product.KIND_SERVICE
                else CommercialLine.SOURCE_STOCK
            )
            for p in Product.objects.filter(is_published=True)
        }
        ctx["customers_for_js"] = [
            {
                "id": customer.pk,
                "name": customer.name,
                "company": customer.company_name,
                "email": customer.email,
                "phone": customer.phone,
                "tax_reference": customer.tax_reference,
            }
            for customer in Customer.objects.all()
        ]
        ctx["templates_for_js"] = [
            {
                "id": template.pk,
                "doc_type": template.doc_type,
                "title": template.title,
                "notes": template.notes,
                "terms": template.terms,
                "pricing_mode": template.pricing_mode,
                "tax_rate": str(template.tax_rate),
                "lines": template.lines,
            }
            for template in DocumentTemplate.objects.filter(is_active=True)
        ]
        ctx["can_view_margin"] = self.request.user.has_perm(
            "billing.view_document_margin"
        )
        ctx["can_revise"] = self.request.user.has_perm(
            "billing.revise_issued_document"
        )
        ctx["can_void"] = self.request.user.has_perm(
            "billing.void_commercial_document"
        )
        return ctx

    def form_valid(self, form):
        persisted = CommercialDocument.objects.prefetch_related("lines").get(
            pk=self.object.pk
        )
        if persisted.is_locked:
            messages.error(
                self.request,
                "This issued document is locked. Start an authorised revision first.",
            )
            return redirect("staff_document_view", pk=self.object.pk)
        discount_value = form.cleaned_data.get("discount_value") or Decimal("0")
        maximum_discount = CompanySettings.load().maximum_unapproved_discount_percent
        if (
            form.cleaned_data.get("discount_type")
            == CommercialDocument.DISCOUNT_PERCENT
            and discount_value > maximum_discount
            and not self.request.user.has_perm("billing.override_document_discount")
        ):
            form.add_error(
                "discount_value",
                f"Discounts above {maximum_discount}% require the discount override permission.",
            )
            return self.form_invalid(form)
        fs = self.get_line_formset()
        if not fs.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, line_formset=fs)
            )
        previous_lines = []
        if self.object and self.object.pk:
            previous_lines = [
                {
                    "pk": line.pk,
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                }
                for line in self.object.lines.all()
            ]
        with transaction.atomic():
            if persisted.revision_number or persisted.status != CommercialDocument.STATUS_DRAFT:
                _create_revision(
                    persisted,
                    self.request.user,
                    self.request.POST.get("revision_reason") or "Document revised",
                )
            self.object = form.save()
            fs.instance = self.object
            fs.save()
            self.object.recalculate_from_lines()
            if self.object.doc_type in (
                CommercialDocument.TYPE_INVOICE,
                CommercialDocument.TYPE_PROFORMA,
            ):
                self.object.sync_payment_status()
            self.object.save(
                update_fields=[
                    "subtotal",
                    "line_discount_amount",
                    "discount_amount",
                    "tax_amount",
                    "withholding_tax_amount",
                    "total",
                    "change_due",
                    "status",
                    "updated_at",
                ]
            )
            _save_walk_in_customer(form, self.object)
            company = CompanySettings.load()
            approval_threshold = company.document_approval_threshold
            approval_required = (
                self.object.status in (
                    CommercialDocument.STATUS_ISSUED,
                    CommercialDocument.STATUS_PAID,
                )
                and approval_threshold > 0
                and self.object.total > approval_threshold
                and not self.request.user.has_perm(
                    "billing.approve_high_value_document"
                )
            )
            if approval_required:
                self.object.status = CommercialDocument.STATUS_DRAFT
                self.object.save(update_fields=["status", "updated_at"])
            if self.object.status in (
                CommercialDocument.STATUS_ISSUED,
                CommercialDocument.STATUS_PAID,
            ):
                requested_status = self.object.status
                try:
                    _issue_document(self.object, self.request.user, "Reissued")
                except ValidationError as exc:
                    self.object.status = CommercialDocument.STATUS_DRAFT
                    self.object.save(update_fields=["status", "updated_at"])
                    messages.warning(
                        self.request,
                        "Saved as draft: " + "; ".join(exc.messages),
                    )
                else:
                    if requested_status == CommercialDocument.STATUS_PAID:
                        self.object.status = requested_status
                        self.object.save(update_fields=["status", "updated_at"])
            _record_receipt_payment(self.object, self.request.user)
            saved_template = _save_document_template(
                form, self.object, self.request.user
            )
        new_lines = [
            {
                "pk": line.pk,
                "description": line.description,
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
        messages.success(
            self.request,
            "Document saved."
            + (f" Saved template “{saved_template.name}”." if saved_template else ""),
        )
        if approval_required:
            messages.warning(
                self.request,
                f"Saved as draft because totals above {company.currency_code} "
                f"{approval_threshold} require high-value approval.",
            )
        for warning in _commercial_warnings(self.object):
            messages.warning(self.request, warning)
        if self.request.POST.get("save_action") == "view":
            return redirect("staff_document_view", pk=self.object.pk)
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
        ctx["pending_payment_submissions"] = doc.payment_submissions.filter(
            status=PaymentSubmission.STATUS_PENDING
        )
        ctx["refund_form"] = PaymentRefundForm()
        ctx["can_refund_payment"] = self.request.user.has_perm(
            "billing.add_paymentrefund"
        )
        ctx["can_reconcile_payment"] = self.request.user.has_perm(
            "billing.change_documentpayment"
        )
        if show_pay and doc.balance_due > 0:
            ctx["payment_request_text"] = (
                f"Hello {doc.display_customer_name}, please pay "
                f"{CompanySettings.load().currency_code} {doc.balance_due:.2f} "
                f"for {doc.get_doc_type_display().lower()} {doc.number}. "
                "Reply with your Mobile Money transaction reference after payment."
            )
            if doc.payment_request_token:
                ctx["payment_request_url"] = self.request.build_absolute_uri(
                    reverse(
                        "payment_request_portal",
                        kwargs={"token": doc.payment_request_token},
                    )
                )
        ctx["can_approve_quote"] = self.request.user.has_perm(
            "billing.approve_high_value_document"
        )
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
            ctx["quote_customer_url"] = self.request.build_absolute_uri(
                reverse("quote_customer_portal", kwargs={"token": doc.quote_customer_token})
            )
        ctx["quote_customer_pending"] = doc.customer_quote_pending
        ctx["quote_customer_accepted"] = doc.quote_customer_accepted is True
        ctx["quote_customer_declined"] = doc.quote_customer_accepted is False
        ctx["revisions"] = doc.revisions.select_related("created_by")
        ctx["customer_credits"] = doc.customer_credits.all()
        ctx["available_credits"] = (
            CustomerCredit.objects.filter(
                customer=doc.customer,
                status=CustomerCredit.STATUS_OPEN,
                remaining_amount__gt=0,
            )
            if doc.customer_id
            else CustomerCredit.objects.none()
        )
        ctx["can_view_margin"] = self.request.user.has_perm(
            "billing.view_document_margin"
        )
        ctx["can_revise"] = self.request.user.has_perm(
            "billing.revise_issued_document"
        )
        ctx["can_void"] = self.request.user.has_perm(
            "billing.void_commercial_document"
        )
        ctx["action_form"] = DocumentActionForm()
        return ctx


@transaction.atomic
def document_record_payment(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(
        CommercialDocument.objects.select_for_update(), pk=pk
    )
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
    applied_amount = min(amount, remaining)
    credit_amount = max(Decimal("0"), amount - remaining)
    DocumentPayment.objects.create(
        document=doc,
        amount=applied_amount,
        method=form.cleaned_data["method"],
        reference=form.cleaned_data.get("reference") or "",
        note=form.cleaned_data.get("note") or "",
        recorded_by=request.user,
    )
    doc.amount_paid = (doc.amount_paid + applied_amount).quantize(Decimal("0.01"))
    if doc.status == CommercialDocument.STATUS_DRAFT:
        doc.status = CommercialDocument.STATUS_ISSUED
    doc.sync_payment_status()
    doc.save(
        update_fields=["amount_paid", "status", "updated_at"]
    )
    if credit_amount > 0:
        CustomerCredit.objects.create(
            customer=doc.customer,
            customer_name=doc.display_customer_name,
            amount=credit_amount,
            remaining_amount=credit_amount,
            source_document=doc,
            reference=form.cleaned_data.get("reference") or "",
            note="Payment exceeded document balance.",
            created_by=request.user,
        )
    log_audit_event(
        actor=request.user,
        verb="billing.payment_recorded",
        summary=f"{doc.number}: +{applied_amount} ({doc.get_status_display()}) balance {doc.balance_due}; credit {credit_amount}",
        target=doc,
    )
    messages.success(
        request,
        f"Recorded payment of {amount}."
        + (
            f" {credit_amount} was saved as customer credit."
            if credit_amount
            else ""
        ),
    )
    return redirect("staff_document_view", pk=pk)


@require_POST
@transaction.atomic
def payment_refund(request, payment_pk: int):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.add_paymentrefund")
    ):
        raise Http404
    payment = get_object_or_404(
        DocumentPayment.objects.select_for_update().select_related(
            "document", "document__customer"
        ),
        pk=payment_pk,
    )
    form = PaymentRefundForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check the refund details.")
        return redirect("staff_document_view", pk=payment.document_id)
    refund = form.save(commit=False)
    refund.payment = payment
    refund.processed_by = request.user
    try:
        refund.full_clean()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_document_view", pk=payment.document_id)
    doc = CommercialDocument.objects.select_for_update().get(pk=payment.document_id)
    credit = CommercialDocument.objects.create(
        doc_type=CommercialDocument.TYPE_CREDIT_NOTE,
        number=allocate_document_number("CRN"),
        **doc.customer_snapshot_kwargs(),
        status=CommercialDocument.STATUS_ISSUED,
        title=f"Refund against {doc.number}",
        issue_date=timezone.localdate(),
        notes=refund.reason,
        subtotal=-refund.amount,
        tax_amount=Decimal("0"),
        total=-refund.amount,
        order=doc.order,
        source_document=doc,
        created_by=request.user,
    )
    refund.credit_note = credit
    refund.save()
    doc.amount_paid = max(Decimal("0"), doc.amount_paid - refund.amount)
    doc.sync_payment_status()
    doc.save(update_fields=["amount_paid", "status", "updated_at"])
    log_audit_event(
        actor=request.user,
        verb="billing.payment_refunded",
        summary=f"{doc.number}: refund {refund.amount}, credit note {credit.number}",
        target=doc,
    )
    messages.success(
        request, f"Refund adjustment and credit note {credit.number} recorded. "
        "Verify the actual return of funds separately with the payment provider."
    )
    return redirect("staff_document_view", pk=doc.pk)


@require_POST
@transaction.atomic
def payment_reconcile(request, payment_pk: int):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.change_documentpayment")
    ):
        raise Http404
    payment = get_object_or_404(
        DocumentPayment.objects.select_for_update(), pk=payment_pk
    )
    if payment.reconciled:
        messages.info(request, "This payment was already reconciled.")
        return redirect("staff_document_view", pk=payment.document_id)
    payment.reconciled = True
    payment.reconciled_at = timezone.now()
    payment.reconciled_by = request.user
    payment.save(
        update_fields=["reconciled", "reconciled_at", "reconciled_by"]
    )
    log_audit_event(
        actor=request.user,
        verb="billing.payment_reconciled",
        summary=f"Payment {payment.pk} on document {payment.document_id}",
        target=payment.document,
    )
    messages.success(request, "Payment marked as reconciled.")
    return redirect("staff_document_view", pk=payment.document_id)


def document_pdf_view(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(
        CommercialDocument.objects.prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    return pdf_response(doc, inline=True, copy=request.GET.get("copy") == "1")


@require_POST
@transaction.atomic
def document_issue(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(
        CommercialDocument.objects.select_for_update().prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    company = CompanySettings.load()
    if (
        company.document_approval_threshold > 0
        and doc.total > company.document_approval_threshold
        and not request.user.has_perm("billing.approve_high_value_document")
    ):
        messages.error(
            request,
            f"Documents above {company.currency_code} "
            f"{company.document_approval_threshold} require high-value approval.",
        )
        return redirect("staff_document_view", pk=pk)
    try:
        _issue_document(doc, request.user)
    except ValidationError as exc:
        transaction.set_rollback(True)
        messages.error(request, "; ".join(exc.messages))
        return redirect("staff_document_view", pk=pk)
    log_audit_event(
        actor=request.user,
        verb="billing.document_issued",
        summary=f"{doc.number} issued and locked",
        target=doc,
    )
    messages.success(request, f"{doc.number} issued and locked.")
    return redirect("staff_document_view", pk=pk)


@require_POST
@transaction.atomic
def document_start_revision(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    if not request.user.has_perm("billing.revise_issued_document"):
        messages.error(request, "You do not have permission to revise issued documents.")
        return redirect("staff_document_view", pk=pk)
    doc = get_object_or_404(
        CommercialDocument.objects.select_for_update().prefetch_related("lines"),
        pk=pk,
    )
    form = DocumentActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A revision reason is required.")
        return redirect("staff_document_view", pk=pk)
    _create_revision(doc, request.user, form.cleaned_data["reason"])
    doc.locked_at = None
    doc.locked_by = None
    if doc.status not in (
        CommercialDocument.STATUS_CANCELLED,
        CommercialDocument.STATUS_PAID,
    ):
        doc.status = CommercialDocument.STATUS_DRAFT
    doc.save(update_fields=["locked_at", "locked_by", "status", "updated_at"])
    log_audit_event(
        actor=request.user,
        verb="billing.document_revision_started",
        summary=f"{doc.number}: {form.cleaned_data['reason']}",
        target=doc,
    )
    messages.success(request, "Revision opened. The previous version is preserved.")
    return redirect("staff_document_edit", pk=pk)


@require_POST
@transaction.atomic
def document_cancel(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    if not request.user.has_perm("billing.void_commercial_document"):
        messages.error(request, "You do not have permission to void documents.")
        return redirect("staff_document_view", pk=pk)
    doc = get_object_or_404(
        CommercialDocument.objects.select_for_update().prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    form = DocumentActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A cancellation reason is required.")
        return redirect("staff_document_view", pk=pk)
    if doc.status == CommercialDocument.STATUS_CANCELLED:
        messages.info(request, "Document is already cancelled.")
        return redirect("staff_document_view", pk=pk)
    _create_revision(doc, request.user, f"Before cancellation: {form.cleaned_data['reason']}")
    if doc.inventory_posted_at and not doc.order_id:
        for line in doc.lines.all():
            if (
                line.source_type == CommercialLine.SOURCE_STOCK
                and line.product_id
                and Decimal(int(line.quantity)) == line.quantity
            ):
                change_stock(
                    product=line.product,
                    product_variant=line.product_variant,
                    quantity_delta=int(line.quantity),
                    movement_type=StockMovement.TYPE_CANCELLATION,
                    reference=doc.number,
                    note="Document voided",
                    actor=request.user,
                )
    doc.status = CommercialDocument.STATUS_CANCELLED
    doc.cancellation_reason = form.cleaned_data["reason"]
    doc.cancelled_at = timezone.now()
    doc.cancelled_by = request.user
    doc.lock(request.user)
    doc.save(
        update_fields=[
            "status",
            "cancellation_reason",
            "cancelled_at",
            "cancelled_by",
            "locked_at",
            "locked_by",
            "updated_at",
        ]
    )
    log_audit_event(
        actor=request.user,
        verb="billing.document_cancelled",
        summary=f"{doc.number}: {doc.cancellation_reason}",
        target=doc,
    )
    messages.success(request, f"{doc.number} cancelled.")
    return redirect("staff_document_view", pk=pk)


@require_POST
@transaction.atomic
def document_duplicate(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    source = get_object_or_404(
        CommercialDocument.objects.prefetch_related("lines"), pk=pk
    )
    copy_fields = [
        "doc_type",
        "title",
        "issue_date",
        "due_date",
        "notes",
        "terms",
        "pricing_mode",
        "tax_rate",
        "tax_exempt",
        "tax_exemption_reason",
        "discount_type",
        "discount_value",
        "shipping_amount",
        "other_charges_label",
        "other_charges",
        "withholding_tax_rate",
        "receipt_payment_method",
        "receipt_payment_reference",
        "hide_prices",
        "location",
        "vehicle_reference",
        "contact_reference",
    ]
    values = {field: getattr(source, field) for field in copy_fields}
    duplicate = CommercialDocument.objects.create(
        number=allocate_document_number(CommercialDocument.PREFIX[source.doc_type]),
        status=CommercialDocument.STATUS_DRAFT,
        source_document=source,
        created_by=request.user,
        salesperson=request.user,
        **source.customer_snapshot_kwargs(),
        **values,
    )
    line_fields = [
        "product",
        "product_variant",
        "source_type",
        "description",
        "sku",
        "serial_number",
        "warranty",
        "line_note",
        "section",
        "sort_order",
        "quantity",
        "unit_price",
        "unit_cost",
        "supplier_name",
        "source_reference",
        "discount_type",
        "discount_value",
        "tax_rate",
        "tax_exempt",
    ]
    for line in source.lines.all():
        CommercialLine.objects.create(
            document=duplicate,
            **{field: getattr(line, field) for field in line_fields},
        )
    duplicate.recalculate_from_lines()
    duplicate.save()
    log_audit_event(
        actor=request.user,
        verb="billing.document_duplicated",
        summary=f"{source.number} duplicated as {duplicate.number}",
        target=duplicate,
    )
    messages.success(request, f"Created draft copy {duplicate.number}.")
    return redirect("staff_document_edit", pk=duplicate.pk)


def account_payment_create(request):
    if not request.user.is_staff:
        raise Http404
    selected_customer = request.POST.get("customer") or request.GET.get("customer")
    initial = {}
    if selected_customer and str(selected_customer).isdigit():
        initial["customer"] = int(selected_customer)
        customer_obj = Customer.objects.filter(pk=int(selected_customer)).first()
        if customer_obj:
            initial["customer_name"] = customer_obj.name
    form = AccountPaymentForm(request.POST or None, initial=initial)
    invoices = CommercialDocument.objects.none()
    if selected_customer and str(selected_customer).isdigit():
        invoices = CommercialDocument.objects.filter(
            customer_id=int(selected_customer),
            doc_type__in=[
                CommercialDocument.TYPE_INVOICE,
                CommercialDocument.TYPE_PROFORMA,
            ],
        ).exclude(
            status__in=[
                CommercialDocument.STATUS_PAID,
                CommercialDocument.STATUS_CANCELLED,
            ]
        )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()
            allocated = Decimal("0")
            for invoice in invoices.select_for_update():
                raw = request.POST.get(f"allocation_{invoice.pk}") or "0"
                try:
                    amount = Decimal(raw)
                except Exception:
                    amount = Decimal("0")
                if amount <= 0:
                    continue
                if amount > invoice.balance_due:
                    form.add_error(
                        None, f"Allocation to {invoice.number} exceeds its balance."
                    )
                    transaction.set_rollback(True)
                    break
                if allocated + amount > payment.amount:
                    form.add_error(None, "Allocations exceed the payment amount.")
                    transaction.set_rollback(True)
                    break
                PaymentAllocation.objects.create(
                    account_payment=payment,
                    document=invoice,
                    amount=amount,
                    allocated_by=request.user,
                )
                DocumentPayment.objects.create(
                    document=invoice,
                    amount=amount,
                    method=payment.method,
                    reference=payment.reference,
                    note=f"Allocated from account payment {payment.pk}",
                    recorded_by=request.user,
                )
                invoice.amount_paid += amount
                invoice.sync_payment_status()
                invoice.save(update_fields=["amount_paid", "status", "updated_at"])
                allocated += amount
            if not transaction.get_rollback():
                remainder = payment.amount - allocated
                if remainder > 0:
                    CustomerCredit.objects.create(
                        customer=payment.customer,
                        customer_name=payment.customer_name,
                        amount=remainder,
                        remaining_amount=remainder,
                        reference=payment.reference,
                        note="Unallocated account payment / overpayment",
                        created_by=request.user,
                    )
                log_audit_event(
                    actor=request.user,
                    verb="billing.account_payment_recorded",
                    summary=f"Account payment {payment.pk}: amount={payment.amount}, allocated={allocated}, credit={remainder}",
                    target=payment,
                )
                messages.success(
                    request,
                    f"Payment recorded; {allocated} allocated"
                    + (f" and {remainder} saved as customer credit." if remainder else "."),
                )
                if payment.customer_id:
                    return redirect(
                        "staff_customer_statement",
                        customer_pk=payment.customer_id,
                    )
                return redirect("staff_documents")
    return render(
        request,
        "billing/account_payment_form.html",
        {"form": form, "invoices": invoices},
    )


def customer_statement(request, customer_pk: int):
    if not request.user.is_staff:
        raise Http404
    customer = get_object_or_404(Customer, pk=customer_pk)
    documents = CommercialDocument.objects.filter(customer=customer).order_by(
        "issue_date", "id"
    )
    payments = AccountPayment.objects.filter(customer=customer)
    credits = CustomerCredit.objects.filter(customer=customer)
    return render(
        request,
        "billing/customer_statement.html",
        {
            "statement_customer": customer,
            "documents": documents,
            "account_payments": payments,
            "credits": credits,
            "total_outstanding": sum(
                (document.balance_due for document in documents), Decimal("0")
            ),
            "total_credit": sum(
                (credit.remaining_amount for credit in credits), Decimal("0")
            ),
        },
    )


def payment_reconciliation(request):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.view_documentpayment")
    ):
        raise Http404
    date_value = request.GET.get("date")
    try:
        selected_date = (
            timezone.datetime.fromisoformat(date_value).date()
            if date_value
            else timezone.localdate()
        )
    except ValueError:
        selected_date = timezone.localdate()
    payments = DocumentPayment.objects.filter(
        recorded_at__date=selected_date
    ).select_related("document", "recorded_by")
    account_payments = AccountPayment.objects.filter(
        recorded_at__date=selected_date
    ).select_related("recorded_by")
    totals = {}
    for method, label in DocumentPayment.METHOD_CHOICES:
        totals[method] = {
            "label": label,
            "document_total": sum(
                (payment.amount for payment in payments if payment.method == method),
                Decimal("0"),
            ),
            "account_total": sum(
                (
                    payment.amount
                    for payment in account_payments
                    if payment.method == method
                ),
                Decimal("0"),
            ),
        }
    return render(
        request,
        "billing/payment_reconciliation.html",
        {
            "selected_date": selected_date,
            "can_review_submissions": request.user.has_perm(
                "billing.change_paymentsubmission"
            ),
            "can_add_account_payment": request.user.has_perm(
                "billing.add_accountpayment"
            ),
            "payments": payments,
            "account_payments": account_payments,
            "method_totals": totals.values(),
            "pending_submissions": PaymentSubmission.objects.filter(
                status=PaymentSubmission.STATUS_PENDING
            ).select_related("document", "document__customer"),
            "recent_submissions": PaymentSubmission.objects.exclude(
                status=PaymentSubmission.STATUS_PENDING
            ).select_related("document", "reviewed_by")[:25],
        },
    )


@require_POST
def payment_submission_approve(request, submission_pk: int):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.change_paymentsubmission")
    ):
        raise Http404
    submission = get_object_or_404(PaymentSubmission, pk=submission_pk)
    try:
        payment = verify_payment_submission(submission, actor=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            f"Verified {payment.reference} and applied {payment.amount} "
            f"to {payment.document.number}.",
        )
    return redirect("staff_payment_reconciliation")


@require_POST
def payment_submission_reject(request, submission_pk: int):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.change_paymentsubmission")
    ):
        raise Http404
    submission = get_object_or_404(PaymentSubmission, pk=submission_pk)
    try:
        reject_payment_submission(
            submission, actor=request.user, reason=request.POST.get("reason", "")
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Payment submission rejected.")
    return redirect("staff_payment_reconciliation")


@require_POST
@transaction.atomic
def apply_customer_credit(request, credit_pk: int, document_pk: int):
    if not request.user.is_staff:
        raise Http404
    credit = get_object_or_404(
        CustomerCredit.objects.select_for_update(), pk=credit_pk
    )
    document = get_object_or_404(
        CommercialDocument.objects.select_for_update(), pk=document_pk
    )
    if credit.status != CustomerCredit.STATUS_OPEN or credit.remaining_amount <= 0:
        messages.error(request, "This credit is no longer available.")
        return redirect("staff_document_view", pk=document_pk)
    if credit.customer_id and document.customer_id != credit.customer_id:
        messages.error(request, "Credit belongs to a different customer.")
        return redirect("staff_document_view", pk=document_pk)
    raw_amount = request.POST.get("amount") or str(credit.remaining_amount)
    try:
        amount = Decimal(raw_amount)
    except Exception:
        amount = Decimal("0")
    amount = min(amount, credit.remaining_amount, document.balance_due)
    if amount <= 0:
        messages.error(request, "Enter a positive credit amount.")
        return redirect("staff_document_view", pk=document_pk)
    DocumentPayment.objects.create(
        document=document,
        amount=amount,
        method=DocumentPayment.METHOD_OTHER,
        reference=credit.reference,
        note=f"Customer credit {credit.pk}",
        recorded_by=request.user,
    )
    document.amount_paid += amount
    document.sync_payment_status()
    document.save(update_fields=["amount_paid", "status", "updated_at"])
    credit.remaining_amount -= amount
    if credit.remaining_amount <= 0:
        credit.remaining_amount = Decimal("0")
        credit.status = CustomerCredit.STATUS_USED
    credit.save(update_fields=["remaining_amount", "status"])
    log_audit_event(
        actor=request.user,
        verb="billing.customer_credit_applied",
        summary=f"Credit {credit.pk}: {amount} applied to {document.number}",
        target=document,
    )
    messages.success(request, f"Applied {amount} customer credit.")
    return redirect("staff_document_view", pk=document_pk)


@require_POST
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
        "credit-note": CommercialDocument.TYPE_CREDIT_NOTE,
    }
    if target not in mapping:
        raise Http404
    new_type = mapping[target]

    if source.status in (
        CommercialDocument.STATUS_CANCELLED,
        CommercialDocument.STATUS_EXPIRED,
    ):
        messages.error(request, "Cancelled or expired documents cannot be converted.")
        return redirect("staff_document_edit", pk=source.pk)

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
    if (
        new_type == CommercialDocument.TYPE_CREDIT_NOTE
        and source.doc_type != CommercialDocument.TYPE_INVOICE
    ):
        messages.error(request, "Credit notes can be created from invoices only.")
        return redirect("staff_document_edit", pk=source.pk)

    prefix = CommercialDocument.PREFIX[new_type]
    with transaction.atomic():
        # Receipts: copy payment totals + history only (no commercial lines needed).
        if new_type == CommercialDocument.TYPE_RECEIPT:
            rec = CommercialDocument.objects.create(
                doc_type=new_type,
                number=allocate_document_number(prefix),
                **source.customer_snapshot_kwargs(),
                status=CommercialDocument.STATUS_ISSUED,
                title=f"Receipt for {source.number}",
                issue_date=source.issue_date,
                due_date=None,
                notes=source.notes,
                terms=source.terms,
                pricing_mode=source.pricing_mode,
                tax_rate=source.tax_rate,
                tax_exempt=source.tax_exempt,
                tax_exemption_reason=source.tax_exemption_reason,
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

        derived_notes = source.notes
        if new_type == CommercialDocument.TYPE_DEMAND_NOTE:
            overdue_days = max(
                0,
                (timezone.localdate() - (source.due_date or source.issue_date)).days,
            )
            demand_context = (
                f"Outstanding balance: {source.balance_due}. "
                f"Overdue by {overdue_days} day(s)."
            )
            derived_notes = (
                f"{source.notes}\n\n{demand_context}".strip()
                if source.notes
                else demand_context
            )
        new_doc = CommercialDocument.objects.create(
            doc_type=new_type,
            number=allocate_document_number(prefix),
            **source.customer_snapshot_kwargs(),
            status=CommercialDocument.STATUS_DRAFT,
            title=(
                f"Delivery note for {source.order.reference}"
                if new_type == CommercialDocument.TYPE_DELIVERY_NOTE and source.order
                else (
                    f"Demand note for {source.number}"
                    if new_type == CommercialDocument.TYPE_DEMAND_NOTE
                    else (
                        f"Credit note for {source.number}"
                        if new_type == CommercialDocument.TYPE_CREDIT_NOTE
                        else source.title
                    )
                )
            ),
            issue_date=source.issue_date,
            due_date=source.due_date,
            notes=derived_notes,
            terms=source.terms,
            pricing_mode=source.pricing_mode,
            tax_rate=source.tax_rate,
            tax_exempt=source.tax_exempt,
            tax_exemption_reason=source.tax_exemption_reason,
            discount_type=source.discount_type,
            discount_value=source.discount_value,
            shipping_amount=source.shipping_amount,
            other_charges_label=source.other_charges_label,
            other_charges=source.other_charges,
            withholding_tax_rate=source.withholding_tax_rate,
            hide_prices=(
                True
                if new_type == CommercialDocument.TYPE_DELIVERY_NOTE
                else source.hide_prices
            ),
            salesperson=source.salesperson,
            location=source.location,
            vehicle_reference=source.vehicle_reference,
            contact_reference=source.contact_reference,
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
                source_type=line.source_type,
                description=line.description,
                sku=line.sku,
                serial_number=line.serial_number,
                warranty=line.warranty,
                line_note=line.line_note,
                section=line.section,
                sort_order=line.sort_order,
                quantity=line.quantity,
                unit_price=line.unit_price,
                unit_cost=line.unit_cost,
                supplier_name=line.supplier_name,
                source_reference=line.source_reference,
                discount_type=line.discount_type,
                discount_value=line.discount_value,
                tax_rate=line.tax_rate,
                tax_exempt=line.tax_exempt,
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
@transaction.atomic
def quote_internal_approve(request, pk: int):
    if not (
        request.user.is_staff
        and request.user.has_perm("billing.approve_high_value_document")
    ):
        raise Http404
    doc = get_object_or_404(
        CommercialDocument.objects.select_for_update(), pk=pk
    )
    if doc.status in (
        CommercialDocument.STATUS_CANCELLED,
        CommercialDocument.STATUS_EXPIRED,
    ):
        messages.error(request, "Cancelled or expired quotations cannot be approved.")
        return redirect("staff_document_view", pk=pk)
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


@require_POST
def payment_request_enable(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    doc = get_object_or_404(CommercialDocument, pk=pk)
    if not doc.supports_payment_request:
        messages.error(request, "Payment links are available for invoices and proformas only.")
        return redirect("staff_document_view", pk=pk)
    if doc.status == CommercialDocument.STATUS_CANCELLED:
        messages.error(request, "Cancelled documents cannot receive payment links.")
        return redirect("staff_document_view", pk=pk)
    if doc.balance_due <= 0:
        messages.info(request, "This document has no outstanding balance.")
        return redirect("staff_document_view", pk=pk)
    doc.ensure_payment_request_token()
    doc.save(update_fields=["payment_request_token", "updated_at"])
    url = request.build_absolute_uri(
        reverse("payment_request_portal", kwargs={"token": doc.payment_request_token})
    )
    log_audit_event(
        actor=request.user,
        verb="billing.payment_link_enabled",
        summary=f"Payment request link enabled for {doc.number}",
        target=doc,
    )
    messages.success(request, f"Payment link ready. Share: {url}")
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


def payment_request_portal(request, token):
    doc = get_object_or_404(
        CommercialDocument.objects.select_related("customer").prefetch_related("lines"),
        payment_request_token=token,
    )
    if not doc.supports_payment_request:
        raise Http404
    company = CompanySettings.load()
    if request.method == "POST":
        try:
            submission, created = submit_payment_confirmation(
                document=doc,
                amount=request.POST.get("amount", ""),
                method=request.POST.get("method", ""),
                reference=request.POST.get("reference", ""),
                payer_name=(request.POST.get("payer_name") or "").strip(),
                payer_email=(request.POST.get("payer_email") or "").strip(),
                payer_phone=(request.POST.get("payer_phone") or "").strip(),
                actor=request.user if request.user.is_authenticated else None,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            if created:
                ContactMessage.objects.create(
                    name=(submission.payer_name or doc.display_customer_name)[:120],
                    email=(
                        submission.payer_email
                        or doc.display_customer_email
                        or "payments@invalid.local"
                    )[:254],
                    phone=submission.payer_phone[:64],
                    subject=f"Payment confirmation for {doc.number}",
                    message=(
                        f"Customer submitted payment confirmation for {doc.number}.\n\n"
                        f"Method: {submission.get_method_display()}\n"
                        f"Amount: {submission.amount}\n"
                        f"Reference: {submission.reference}\n"
                        f"Customer: {submission.payer_name}\n"
                        f"Email: {submission.payer_email}\n"
                        f"Phone: {submission.payer_phone}"
                    ),
                )
                messages.success(
                    request,
                    "Thank you. Your payment reference was submitted for verification.",
                )
            else:
                messages.info(
                    request,
                    "This payment reference was already submitted and is being reviewed.",
                )
            return redirect("payment_request_portal", token=token)
    return render(
        request,
        "billing/payment_request.html",
        {
            "document": doc,
            "company": company,
            "pending_submissions": doc.payment_submissions.filter(
                status=PaymentSubmission.STATUS_PENDING
            ),
            "payment_methods": DocumentPayment.METHOD_CHOICES,
        },
    )
