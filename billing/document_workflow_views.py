from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from billing import views
from billing.forms import CommercialDocumentForm
from billing.models import CommercialDocument


class WalkInCommercialDocumentForm(CommercialDocumentForm):
    def __init__(self, *args, **kwargs):
        args = list(args)
        if args and hasattr(args[0], "copy"):
            data = args[0].copy()
            if not data.get("customer") and not (data.get("customer_name") or "").strip():
                data["customer_name"] = "Walk-in customer"
            args[0] = data
        elif kwargs.get("data") is not None and hasattr(kwargs["data"], "copy"):
            data = kwargs["data"].copy()
            if not data.get("customer") and not (data.get("customer_name") or "").strip():
                data["customer_name"] = "Walk-in customer"
            kwargs["data"] = data
        super().__init__(*args, **kwargs)


class CommercialDocumentListView(views.CommercialDocumentListView):
    def get_queryset(self):
        CommercialDocument.objects.filter(
            doc_type=CommercialDocument.TYPE_QUOTE,
            due_date__lt=timezone.localdate(),
            status__in=[CommercialDocument.STATUS_DRAFT, CommercialDocument.STATUS_ISSUED],
        ).update(status=CommercialDocument.STATUS_EXPIRED)
        qs = CommercialDocument.objects.select_related("customer").order_by("-created_at", "-id")
        document_type = self.request.GET.get("type")
        if document_type in dict(CommercialDocument.TYPE_CHOICES):
            qs = qs.filter(doc_type=document_type)
        status = self.request.GET.get("status")
        if status in dict(CommercialDocument.STATUS_CHOICES):
            qs = qs.filter(status=status)
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(
                Q(number__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(customer_company__icontains=query)
                | Q(customer_email__icontains=query)
                | Q(customer_phone__icontains=query)
                | Q(customer__name__icontains=query)
                | Q(customer__company_name__icontains=query)
                | Q(title__icontains=query)
                | Q(contact_reference__icontains=query)
            )
        return qs


class CommercialDocumentCreateView(views.CommercialDocumentCreateView):
    form_class = WalkInCommercialDocumentForm

    def form_invalid(self, form):
        messages.error(
            self.request,
            "The document was not saved. Check the highlighted fields and line items, then try again.",
        )
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("save_action") == "pdf" and self.object:
            return redirect(f"{reverse('staff_document_pdf', kwargs={'pk': self.object.pk})}?download=1")
        return response


class CommercialDocumentUpdateView(views.CommercialDocumentUpdateView):
    form_class = WalkInCommercialDocumentForm

    def form_invalid(self, form):
        messages.error(
            self.request,
            "The document was not saved. Check the highlighted fields and line items, then try again.",
        )
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("save_action") == "pdf" and self.object:
            return redirect(f"{reverse('staff_document_pdf', kwargs={'pk': self.object.pk})}?download=1")
        return response
