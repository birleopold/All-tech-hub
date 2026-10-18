from __future__ import annotations

import csv

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, DecimalField, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.views import View

from billing.models import CommercialDocument, CommercialLine
from catalog.models import Product, ProductReview
from catalog.quality import catalogue_quality_rows
from commerce.models import Order, OrderLine
from core.audit import log_audit_event
from core.mixins import StaffRequiredMixin
from growth.models import ProductGrowthData
from inventory.forms import (
    ProductCommerceProfileForm,
    ProductCommercialCoreForm,
    ProductGrowthDataForm,
)
from inventory.models import StockMovement
from marketing.models import MarketingLead, ScheduledPost
from purchasing.models import PurchaseLine
from merchandising.enrichment import (
    apply_bulk_catalogue_enrichment,
    product_inventory_state,
)
from merchandising.forms import BulkCatalogueEnrichmentForm
from merchandising.models import ProductCommerceProfile
from merchandising.management.commands.export_google_review_queue import build_google_review_rows


class ProductCommercialReviewView(StaffRequiredMixin, View):
    template_name = "dashboard/product_commercial_review.html"

    def get_product(self, pk: int) -> Product:
        return get_object_or_404(
            Product.objects.select_related(
                "category", "growth_data", "commerce_profile"
            ).prefetch_related("gallery_images", "variants"),
            pk=pk,
            kind=Product.KIND_PHYSICAL,
        )

    @staticmethod
    def related_instances(product: Product):
        try:
            growth = product.growth_data
        except ObjectDoesNotExist:
            growth = ProductGrowthData(product=product)
        try:
            profile = product.commerce_profile
        except ObjectDoesNotExist:
            profile = ProductCommerceProfile(product=product)
        return growth, profile

    def build_forms(self, product: Product, data=None):
        growth, profile = self.related_instances(product)
        return (
            ProductCommercialCoreForm(data=data, instance=product, prefix="core"),
            ProductGrowthDataForm(data=data, instance=growth, prefix="growth"),
            ProductCommerceProfileForm(
                data=data, instance=profile, prefix="commerce"
            ),
        )

    def context(self, product: Product, forms):
        core_form, growth_form, commerce_form = forms
        _, profile = self.related_instances(product)
        missing = profile.merchant_missing_fields()
        context = {
            "product": product,
            "core_form": core_form,
            "growth_form": growth_form,
            "commerce_form": commerce_form,
            "merchant_missing_fields": missing,
            "merchant_readiness_score": profile.merchant_readiness_score,
            "merchant_ready": not missing,
        }
        user = self.request.user
        context["product_access"] = {
            "sales": user.has_perm("commerce.view_order"),
            "finance": user.has_perm("billing.view_commercialline"),
            "purchasing": user.has_perm("purchasing.view_purchaseline"),
            "inventory": user.has_perm("inventory.view_stockmovement"),
            "marketing": user.has_perm("marketing.view_marketinglead"),
            "posts": user.has_perm("marketing.view_scheduledpost"),
        }
        access = context["product_access"]
        if access["sales"]:
            lines = OrderLine.objects.filter(product=product).exclude(
                order__status=Order.STATUS_CANCELLED)
            context["product_sales"] = lines.aggregate(
                units=Sum("quantity"),
                gross=Sum(F("quantity") * F("unit_price"),
                          output_field=DecimalField(max_digits=18, decimal_places=2)),
            )
        if access["finance"]:
            invoice_lines = CommercialLine.objects.filter(
                product=product, document__doc_type=CommercialDocument.TYPE_INVOICE
            ).exclude(document__status__in=[
                CommercialDocument.STATUS_DRAFT, CommercialDocument.STATUS_CANCELLED,
                CommercialDocument.STATUS_EXPIRED,
            ]).select_related("document").order_by("-document__issue_date", "-pk")
            counted = 0
            known = 0
            gross_profit = 0
            for line in invoice_lines.iterator(chunk_size=200):
                counted += 1
                if line.unit_cost > 0:
                    known += 1
                    gross_profit += line.gross_profit
            context["product_margin"] = {
                "profit": gross_profit, "covered": known, "total": counted,
            }
        if access["purchasing"]:
            context["last_purchase"] = PurchaseLine.objects.filter(
                product=product).select_related(
                "purchase_order", "purchase_order__supplier"
            ).order_by("-purchase_order__ordered_on", "-pk").first()
        if access["inventory"]:
            context["recent_movements"] = StockMovement.objects.filter(
                product=product).order_by("-created_at")[:6]
        if access["marketing"]:
            context["product_lead_count"] = MarketingLead.objects.filter(
                product=product).count()
        if access["posts"]:
            context["recent_social_posts"] = ScheduledPost.objects.filter(
                product=product).order_by("-created_at")[:5]
        context["product_review_rating"] = ProductReview.objects.filter(
            product=product, is_published=True).aggregate(
            average=Avg("rating"))["average"]
        return context

    def get(self, request, pk: int):
        product = self.get_product(pk)
        forms = self.build_forms(product)
        return render(request, self.template_name, self.context(product, forms))

    def post(self, request, pk: int):
        product = self.get_product(pk)
        forms = self.build_forms(product, data=request.POST)
        core_form, growth_form, commerce_form = forms
        validation_results = [form.is_valid() for form in forms]

        if all(validation_results):
            with transaction.atomic():
                product = core_form.save()
                growth = growth_form.save(commit=False)
                growth.product = product
                growth.save()
                profile = commerce_form.save(commit=False)
                profile.product = product
                profile.save()

            log_audit_event(
                actor=request.user,
                verb="catalog.commercial_profile_reviewed",
                summary=(
                    f"Reviewed commercial facts for ‘{product.name}’ — "
                    f"Merchant readiness {profile.merchant_readiness_score}%"
                ),
                target=product,
            )
            messages.success(
                request,
                (
                    "Commercial product facts saved. Merchant readiness is now "
                    f"{profile.merchant_readiness_score}%."
                ),
            )
            return redirect("staff_product_commercial_review", pk=product.pk)

        messages.error(request, "Correct the highlighted fields before saving.")
        return render(request, self.template_name, self.context(product, forms))


class CatalogueBulkEnrichmentView(StaffRequiredMixin, View):
    template_name = "dashboard/catalogue_bulk_enrichment.html"
    page_size = 60

    @staticmethod
    def base_queryset():
        return (
            Product.objects.filter(kind=Product.KIND_PHYSICAL)
            .select_related("category", "growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )

    def filtered_products(self, request):
        queryset = self.base_queryset()
        query = (request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(sku__icontains=query)
                | Q(category__name__icontains=query)
                | Q(growth_data__brand__icontains=query)
                | Q(growth_data__mpn__icontains=query)
            ).distinct()
        return list(queryset), query

    def build_rows(self, products, gap: str):
        quality_by_id = {
            row.product.pk: row for row in catalogue_quality_rows(products)
        }
        rows = []
        for product in products:
            try:
                growth = product.growth_data
            except ObjectDoesNotExist:
                growth = None
            try:
                profile = product.commerce_profile
            except ObjectDoesNotExist:
                profile = None
            merchant_missing = (
                profile.merchant_missing_fields()
                if profile is not None
                else ["commercial profile"]
            )
            missing_alt = any(
                image.image and not image.alt_text.strip()
                for image in product.gallery_images.all()
            )
            inventory_managed, available = product_inventory_state(product)
            condition_verified = bool(
                profile is not None and profile.condition_verified_at
            )
            matches_gap = {
                "": True,
                "no_sku": not product.sku.strip(),
                "no_brand": growth is None or not growth.brand.strip(),
                "no_profile": profile is None,
                "no_alt": missing_alt,
                "out_of_stock": inventory_managed and not available,
                "merchant_not_ready": bool(merchant_missing),
            }.get(gap, True)
            if not matches_gap:
                continue
            rows.append(
                {
                    "product": product,
                    "quality": quality_by_id[product.pk],
                    "brand": growth.brand if growth else "",
                    "condition": (
                        growth.get_condition_display()
                        if growth and condition_verified
                        else ""
                    ),
                    "condition_unverified": bool(growth and not condition_verified),
                    "profile": profile,
                    "merchant_score": profile.merchant_readiness_score if profile else 0,
                    "merchant_missing": merchant_missing,
                    "missing_alt": missing_alt,
                    "available": available,
                    "inventory_managed": inventory_managed,
                }
            )
        return rows

    def form_choices(self):
        return list(
            Product.objects.filter(kind=Product.KIND_PHYSICAL)
            .order_by("name", "pk")
            .values_list("pk", "name")
        )

    def context(self, request, *, form=None):
        products, query = self.filtered_products(request)
        gap = (request.GET.get("gap") or "").strip()
        valid_gaps = {
            "",
            "no_sku",
            "no_brand",
            "no_profile",
            "no_alt",
            "out_of_stock",
            "merchant_not_ready",
        }
        if gap not in valid_gaps:
            gap = ""
        rows = self.build_rows(products, gap)
        paginator = Paginator(rows, self.page_size)
        page_obj = paginator.get_page(request.GET.get("page"))
        if form is None:
            form = BulkCatalogueEnrichmentForm(
                product_choices=self.form_choices()
            )
        return {
            "bulk_form": form,
            "enrichment_rows": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": paginator.num_pages > 1,
            "current_query": query,
            "current_gap": gap,
            "matching_count": len(rows),
        }

    def get(self, request):
        return render(request, self.template_name, self.context(request))

    def post(self, request):
        form = BulkCatalogueEnrichmentForm(
            request.POST,
            product_choices=self.form_choices(),
        )
        if form.is_valid():
            product_ids = [int(value) for value in form.cleaned_data["product_ids"]]
            products = list(
                self.base_queryset().filter(pk__in=product_ids).order_by("name", "pk")
            )
            if len(products) != len(set(product_ids)):
                messages.error(
                    request,
                    "One or more selected products are no longer available for enrichment.",
                )
            else:
                result = apply_bulk_catalogue_enrichment(
                    products=products,
                    cleaned_data=form.cleaned_data,
                    actor=request.user,
                )
                messages.success(
                    request,
                    (
                        f"Processed {result.get('products_processed', 0)} products. "
                        f"Generated {result.get('skus_generated', 0)} SKUs, completed "
                        f"{result.get('alt_text_completed', 0)} alt-text records and "
                        f"unpublished {result.get('products_unpublished', 0)} unavailable listings."
                    ),
                )
                return redirect("staff_catalogue_bulk_enrichment")
        else:
            messages.error(request, "Correct the bulk enrichment form before applying it.")
        return render(
            request,
            self.template_name,
            self.context(request, form=form),
        )


class GoogleReviewQueueDownloadView(StaffRequiredMixin, View):
    """Staff-only, read-only spreadsheet of actual outstanding Merchant checks."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="leosoft-google-review-queue.csv"'
        response.write("\ufeff")
        columns = (
            "product_id", "product_name", "category", "stock_quantity",
            "stock_tracked", "merchant_approved", "merchant_score",
            "missing_checks", "review_path",
        )
        writer = csv.DictWriter(response, fieldnames=columns)
        writer.writeheader()
        writer.writerows(build_google_review_rows())
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
