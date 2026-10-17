from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView, UpdateView

from billing.models import CommercialLine
from catalog.models import Product, ProductImage, ProductSerial, ProductVariant
from catalog.stock_alerts import low_stock_products
from core.audit import log_audit_event
from core.barcodes import label_payload, repeated_labels
from core.mixins import StaffRequiredMixin
from core.models import SupportTicket
from growth.models import ProductGrowthData
from inventory.forms import (
    JobStockUseForm,
    ProductStaffForm,
    ProductCommerceProfileForm,
    ProductGrowthDataForm,
    StockAdjustmentForm,
)
from inventory.models import StockAdjustment, StockMovement, StockTake, StockTakeLine
from inventory.product_identity import conflicting_sku, normal_sku, same_name_products
from merchandising.models import ProductCommerceProfile
from operations.models import JobCard


class AllowEmptyExtraInlineFormSet(BaseInlineFormSet):
    """Extra blank rows do not block save (for optional new gallery / variant lines)."""

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if i >= self.initial_form_count():
            form.empty_permitted = True
        return form


ProductImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    fields=("image", "sort_order", "alt_text"),
    extra=1,
    can_delete=True,
    formset=AllowEmptyExtraInlineFormSet,
)

class ValidatedVariantFormSet(AllowEmptyExtraInlineFormSet):
    """Catch newly reused SKUs, including duplicates in the same submission."""

    parent_sku = ""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        groups = {}
        for form in self.forms:
            data = getattr(form, "cleaned_data", None)
            if not data or data.get("DELETE"):
                continue
            sku = normal_sku(data.get("sku"))
            if sku:
                old_sku = normal_sku(form.initial.get("sku"))
                changed = not form.instance.pk or sku != old_sku
                groups.setdefault(sku, []).append((form, changed))
        for sku, forms in groups.items():
            for form, changed in forms:
                if not changed:
                    continue
                if len(forms) > 1:
                    form.add_error("sku", "This SKU is used by another option here.")
                elif sku == normal_sku(self.parent_sku):
                    form.add_error("sku", "A variant cannot reuse the main product SKU.")
                else:
                    conflict = conflicting_sku(sku, exclude_variant=form.instance.pk)
                    if conflict:
                        form.add_error("sku", f"SKU belongs to {conflict['name']}.")


ProductVariantFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    fields=(
        "name",
        "sku",
        "price",
        "compare_at_price",
        "track_inventory",
        "stock_quantity",
        "sort_order",
        "is_active",
    ),
    extra=1,
    can_delete=True,
    formset=ValidatedVariantFormSet,
)

class InventoryHomeView(StaffRequiredMixin, TemplateView):
    template_name = "inventory/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["adjustment_form"] = StockAdjustmentForm()
        ctx["recent_adjustments"] = (
            StockAdjustment.objects.select_related(
                "product", "product_variant", "created_by"
            )[:12]
        )
        ctx["recent_movements"] = StockMovement.objects.select_related(
            "product", "product_variant", "actor"
        )[:25]
        ctx["low_stock_items"] = low_stock_products(limit=15)
        return ctx


class StockMovementListView(StaffRequiredMixin, ListView):
    model = StockMovement
    template_name = "inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 50

    def get_queryset(self):
        return StockMovement.objects.select_related(
            "product", "product_variant", "actor"
        )


class WarrantyCenterView(StaffRequiredMixin, TemplateView):
    template_name = "inventory/warranty_center.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()
        ctx["q"] = q
        ctx["serials"] = []
        ctx["jobs"] = []
        ctx["tickets"] = []
        ctx["document_lines"] = []
        if not q:
            return ctx

        serials = (
            ProductSerial.objects.select_related("product", "product_variant", "sold_to")
            .prefetch_related("support_tickets")
            .filter(
                Q(serial_number__icontains=q)
                | Q(imei__icontains=q)
                | Q(mac_address__icontains=q)
                | Q(product__name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product_variant__sku__icontains=q)
                | Q(sold_to__name__icontains=q)
                | Q(sold_to__email__icontains=q)
                | Q(sold_to__phone__icontains=q)
            )
            .distinct()[:25]
        )
        ctx["serials"] = serials
        ctx["jobs"] = (
            JobCard.objects.select_related("customer", "assigned_to")
            .filter(
                Q(number__icontains=q)
                | Q(title__icontains=q)
                | Q(device_make__icontains=q)
                | Q(device_model__icontains=q)
                | Q(serial_number__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__email__icontains=q)
                | Q(customer__phone__icontains=q)
            )
            .distinct()[:25]
        )
        ctx["tickets"] = (
            SupportTicket.objects.select_related(
                "customer",
                "related_serial",
                "related_serial__product",
                "assigned_to",
            )
            .filter(
                Q(reference__icontains=q)
                | Q(subject__icontains=q)
                | Q(category__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__email__icontains=q)
                | Q(customer__phone__icontains=q)
                | Q(related_serial__serial_number__icontains=q)
                | Q(related_serial__imei__icontains=q)
                | Q(related_serial__mac_address__icontains=q)
            )
            .distinct()[:25]
        )
        ctx["document_lines"] = (
            CommercialLine.objects.select_related(
                "document",
                "document__customer",
                "product",
                "product_variant",
            )
            .filter(
                Q(serial_number__icontains=q)
                | Q(description__icontains=q)
                | Q(sku__icontains=q)
                | Q(warranty__icontains=q)
                | Q(document__number__icontains=q)
                | Q(document__customer_name__icontains=q)
                | Q(document__customer_email__icontains=q)
                | Q(document__customer_phone__icontains=q)
                | Q(document__customer__name__icontains=q)
                | Q(document__customer__email__icontains=q)
                | Q(document__customer__phone__icontains=q)
            )
            .distinct()[:25]
        )
        return ctx


class ProductManageListView(StaffRequiredMixin, ListView):
    template_name = "inventory/product_list.html"
    context_object_name = "products"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category")
            .prefetch_related("variants")
            .order_by("category__sort_order", "name")
        )
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(category__name__icontains=q)
                | Q(variants__sku__icontains=q)
            ).distinct()
        if self.request.GET.get("low") == "1":
            low_ids = [p.pk for p in low_stock_products(limit=None)]
            qs = qs.filter(pk__in=low_ids) if low_ids else qs.none()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q") or ""
        return ctx


@login_required
@require_GET
def product_identity_check(request):
    """Staff-only lookup for duplicate names and conflicting SKUs."""
    if not request.user.is_staff:
        raise Http404
    try:
        product_id = int(request.GET.get("product_id") or 0)
    except (ValueError, TypeError):
        product_id = 0
    return JsonResponse({
        "name_matches": same_name_products(
            (request.GET.get("name") or "")[:200], exclude_product=product_id
        ),
        "sku_conflict": conflicting_sku(
            (request.GET.get("sku") or "")[:64], exclude_product=product_id
        ),
    })


class ProductRelatedFormsMixin:
    """Keep product identity, condition and specifications on the main workspace."""

    @staticmethod
    def related_instances(product):
        try:
            growth = product.growth_data
        except ObjectDoesNotExist:
            growth = ProductGrowthData(product=product)
        try:
            commerce = product.commerce_profile
        except ObjectDoesNotExist:
            commerce = ProductCommerceProfile(product=product)
        return growth, commerce

    def related_forms(self, product=None, data=None):
        growth = ProductGrowthData(product=product) if product is None else self.related_instances(product)[0]
        commerce = ProductCommerceProfile(product=product) if product is None else self.related_instances(product)[1]
        return (
            ProductGrowthDataForm(data=data, instance=growth, prefix="growth"),
            ProductCommerceProfileForm(data=data, instance=commerce, prefix="commerce"),
        )


class ProductCreateView(ProductRelatedFormsMixin, StaffRequiredMixin, CreateView):
    model = Product
    form_class = ProductStaffForm
    template_name = "inventory/product_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if "growth_form" not in ctx:
            ctx["growth_form"], ctx["commerce_form"] = self.related_forms()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        growth_form, commerce_form = self.related_forms(data=request.POST)
        validations = (
            form.is_valid(),
            growth_form.is_valid(),
            commerce_form.is_valid(),
        )
        if all(validations):
            with transaction.atomic():
                self.object = form.save()
                growth = growth_form.save(commit=False)
                growth.product = self.object
                growth.save()
                commerce = commerce_form.save(commit=False)
                commerce.product = self.object
                commerce.save()
            log_audit_event(
                actor=request.user,
                verb="catalog.product_saved",
                summary=f"Created “{self.object.name}” published={self.object.is_published}",
                target=self.object,
            )
            messages.success(
                request,
                "Product, condition and specifications saved. Add gallery images and variants below.",
            )
            edit_url = reverse("staff_product_edit", kwargs={"pk": self.object.pk})
            if "send_photos_to_phone" in request.POST:
                return redirect(f"{edit_url}?photos=phone")
            return redirect(edit_url)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                growth_form=growth_form,
                commerce_form=commerce_form,
            )
        )


class ProductUpdateView(ProductRelatedFormsMixin, StaffRequiredMixin, UpdateView):
    model = Product
    form_class = ProductStaffForm
    template_name = "inventory/product_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if "image_formset" in kwargs:
            ctx["image_formset"] = kwargs["image_formset"]
            ctx["variant_formset"] = kwargs["variant_formset"]
        elif self.request.method == "POST":
            ctx["image_formset"] = ProductImageFormSet(
                self.request.POST, self.request.FILES, instance=self.object
            )
            ctx["variant_formset"] = ProductVariantFormSet(
                self.request.POST, instance=self.object
            )
        else:
            ctx["image_formset"] = ProductImageFormSet(instance=self.object)
            ctx["variant_formset"] = ProductVariantFormSet(instance=self.object)
        if "growth_form" not in ctx:
            ctx["growth_form"], ctx["commerce_form"] = self.related_forms(self.object)
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        image_fs = ProductImageFormSet(
            request.POST, request.FILES, instance=self.object
        )
        variant_fs = ProductVariantFormSet(request.POST, instance=self.object)
        growth_form, commerce_form = self.related_forms(
            self.object, data=request.POST
        )
        core_valid = form.is_valid()
        variant_fs.parent_sku = (
            form.cleaned_data.get("sku", "") if core_valid else self.object.sku
        )
        validations = (
            core_valid,
            image_fs.is_valid(),
            variant_fs.is_valid(),
            growth_form.is_valid(),
            commerce_form.is_valid(),
        )
        if all(validations):
            with transaction.atomic():
                self.object = form.save()
                image_fs.instance = self.object
                image_fs.save()
                variant_fs.instance = self.object
                variant_fs.save()
                growth = growth_form.save(commit=False)
                growth.product = self.object
                growth.save()
                commerce = commerce_form.save(commit=False)
                commerce.product = self.object
                commerce.save()
            log_audit_event(
                actor=request.user,
                verb="catalog.product_saved",
                summary=f"Updated “{self.object.name}” published={self.object.is_published}",
                target=self.object,
            )
            messages.success(
                request, "Product, condition and specifications saved."
            )
            return redirect(self.get_success_url())
        return self.render_to_response(
            self.get_context_data(
                form=form,
                image_formset=image_fs,
                variant_formset=variant_fs,
                growth_form=growth_form,
                commerce_form=commerce_form,
            )
        )

    def get_success_url(self):
        return reverse("staff_product_edit", kwargs={"pk": self.object.pk})


def _label_copies(request) -> int:
    try:
        return int(request.GET.get("copies") or 1)
    except ValueError:
        return 1


def _safe_redirect_target(request, fallback: str):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return fallback


def product_label_sheet(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("variants"), pk=pk
    )
    labels = []
    active_variants = [v for v in product.variants.all() if v.is_active]
    if active_variants:
        for variant in active_variants:
            labels.append(
                label_payload(
                    "Product option",
                    product.name,
                    variant.sku or f"V-{variant.pk}",
                    subtitle=variant.name,
                    meta=f"{product.category.name} / Product #{product.pk} / Variant #{variant.pk}",
                )
            )
    else:
        labels.append(
            label_payload(
                "Product",
                product.name,
                product.sku or f"P-{product.pk}",
                subtitle=product.category.name,
                meta=f"Product #{product.pk}",
            )
        )
    return render(
        request,
        "core/label_sheet.html",
        {
            "title": f"Product labels - {product.name}",
            "labels": repeated_labels(labels, _label_copies(request)),
            "back_url": reverse("staff_product_edit", kwargs={"pk": product.pk}),
        },
    )


def serial_label_sheet(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    serial = get_object_or_404(
        ProductSerial.objects.select_related("product", "product_variant", "sold_to"),
        pk=pk,
    )
    labels = [
        label_payload(
            "Serial",
            serial.product.name,
            serial.serial_number,
            subtitle=serial.product_variant.name if serial.product_variant else "",
            meta=(
                f"{serial.get_status_display()}"
                + (f" / {serial.sold_to.name}" if serial.sold_to else "")
                + (f" / Warranty until {serial.warranty_expires_on}" if serial.warranty_expires_on else "")
            ),
        )
    ]
    return render(
        request,
        "core/label_sheet.html",
        {
            "title": f"Serial label - {serial.serial_number}",
            "labels": repeated_labels(labels, _label_copies(request)),
            "back_url": reverse("staff_search") + f"?q={serial.serial_number}",
        },
    )


def create_stock_adjustment(request):
    if not request.user.is_staff:
        raise Http404
    if request.method != "POST":
        return redirect("staff_inventory")
    form = StockAdjustmentForm(request.POST)
    if form.is_valid():
        adj = form.save(commit=False)
        adj.created_by = request.user
        adj.save()
        try:
            adj.apply()
        except ValidationError as exc:
            adj.delete()
            messages.error(request, "; ".join(exc.messages))
            return redirect("staff_inventory")

        label = adj.product.name
        if adj.product_variant_id:
            label = f"{adj.product.name} ({adj.product_variant.name})"
        job_bit = f" · {adj.job.number}" if adj.job_id else ""
        log_audit_event(
            actor=request.user,
            verb="inventory.stock_adjust",
            summary=f"{label}: {adj.quantity_delta:+d} ({adj.get_reason_display()}){job_bit}",
            target=adj,
        )
        messages.success(request, "Stock adjusted.")
    else:
        messages.error(request, "Could not adjust stock.")
    return redirect("staff_inventory")


class StockTakeListView(StaffRequiredMixin, ListView):
    template_name = "inventory/stocktake_list.html"
    context_object_name = "takes"
    paginate_by = 25

    def get_queryset(self):
        return StockTake.objects.select_related("created_by").all()


class StockTakeDetailView(StaffRequiredMixin, DetailView):
    model = StockTake
    template_name = "inventory/stocktake_detail.html"
    context_object_name = "take"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lines"] = self.object.lines.select_related(
            "product", "product_variant"
        ).all()
        return ctx


def stocktake_label_sheet(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    take = get_object_or_404(
        StockTake.objects.prefetch_related("lines__product", "lines__product_variant"),
        pk=pk,
    )
    labels = [
        label_payload(
            "Stock take",
            take.reference,
            take.reference,
            subtitle=take.name,
            meta=take.get_status_display(),
        )
    ]
    for line in take.lines.all():
        code = line.product_variant.sku if line.product_variant else line.product.sku
        labels.append(
            label_payload(
                "Count line",
                line.product.name,
                code or f"P-{line.product_id}",
                subtitle=line.product_variant.name if line.product_variant else "",
                meta=f"{take.reference} / System {line.system_quantity} / Line #{line.pk}",
            )
        )
    return render(
        request,
        "core/label_sheet.html",
        {
            "title": f"Stock take labels - {take.reference}",
            "labels": repeated_labels(labels, _label_copies(request)),
            "back_url": reverse("staff_stocktake_detail", kwargs={"pk": take.pk}),
        },
    )


@require_POST
def stocktake_create(request):
    if not request.user.is_staff:
        raise Http404
    name = (request.POST.get("name") or "").strip()
    note = (request.POST.get("note") or "").strip()
    take = StockTake.objects.create(name=name, note=note, created_by=request.user)
    messages.success(request, f"Stock take {take.reference} created. Add lines below.")
    return redirect("staff_stocktake_detail", pk=take.pk)


@require_POST
def stocktake_add_line(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    take = get_object_or_404(StockTake, pk=pk)
    if not take.is_open:
        messages.error(request, "Stock take is no longer open.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    product_id = request.POST.get("product")
    variant_id = request.POST.get("product_variant") or None
    counted_raw = (request.POST.get("counted_quantity") or "").strip()
    if not product_id or not counted_raw:
        messages.error(request, "Choose a product and enter a counted quantity.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    try:
        counted = int(counted_raw)
    except ValueError:
        messages.error(request, "Counted quantity must be a whole number.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    if counted < 0:
        messages.error(request, "Counted stock cannot be negative.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    product = get_object_or_404(Product, pk=product_id)
    variant = None
    if variant_id:
        variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    if product.kind != Product.KIND_PHYSICAL:
        messages.error(request, "Services do not have physical stock to count.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    if variant:
        trackable = variant.track_inventory
    else:
        trackable = product.track_inventory and not product.has_sellable_variants()
    if not trackable:
        messages.error(request, "Choose an inventory-tracked product or configuration.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    if StockTakeLine.objects.filter(
        take=take, product=product, product_variant=variant
    ).exists():
        messages.error(request, "This item already has a count line.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    system_qty = variant.stock_quantity if variant else product.stock_quantity
    StockTakeLine.objects.create(
        take=take,
        product=product,
        product_variant=variant,
        system_quantity=int(system_qty or 0),
        counted_quantity=counted,
        note=(request.POST.get("note") or "")[:255],
    )
    messages.success(request, "Line added.")
    return redirect("staff_stocktake_detail", pk=take.pk)


@require_POST
def stocktake_post(request, pk: int):
    if not request.user.is_staff:
        raise Http404
    take = get_object_or_404(StockTake, pk=pk)
    if not take.is_open:
        messages.error(request, "Stock take is already finalised.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    try:
        count = take.post(actor=request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("staff_stocktake_detail", pk=take.pk)
    if take.status != StockTake.STATUS_POSTED:
        messages.info(request, "This stock take was already finalised.")
        return redirect("staff_stocktake_detail", pk=take.pk)
    log_audit_event(
        actor=request.user,
        verb="inventory.stocktake_posted",
        summary=f"{take.reference}: {count} lines posted",
        target=take,
    )
    messages.success(request, f"Posted {count} lines — variances applied to stock.")
    return redirect("staff_stocktake_detail", pk=take.pk)


@transaction.atomic
def job_record_part_usage(request, job_pk: int):
    if not request.user.is_staff:
        raise Http404
    if request.method != "POST":
        return redirect(_safe_redirect_target(request, reverse("staff_job_detail", kwargs={"pk": job_pk})))
    job = get_object_or_404(JobCard.objects.select_for_update(), pk=job_pk)
    if not job.is_open:
        messages.error(
            request, "Parts cannot be consumed after a job is completed or cancelled."
        )
        return redirect("staff_job_detail", pk=job_pk)
    form = JobStockUseForm(request.POST)
    if form.is_valid():
        adj = form.save(commit=False)
        adj.job = job
        adj.created_by = request.user
        adj.reason = StockAdjustment.REASON_JOB
        adj.save()
        try:
            adj.apply()
        except ValidationError as exc:
            adj.delete()
            messages.error(request, "; ".join(exc.messages))
            return redirect(_safe_redirect_target(request, reverse("staff_job_detail", kwargs={"pk": job_pk})))

        label = adj.product.name
        if adj.product_variant_id:
            label = f"{adj.product.name} ({adj.product_variant.name})"
        log_audit_event(
            actor=request.user,
            verb="inventory.job_part_use",
            summary=f"{job.number}: {label} {adj.quantity_delta:+d}",
            target=adj,
        )
        messages.success(request, "Parts usage recorded and stock updated.")
    else:
        messages.error(request, "Could not record parts — check product, variant, and quantity.")
    return redirect(_safe_redirect_target(request, reverse("staff_job_detail", kwargs={"pk": job_pk})))
