from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from catalog.models import Product
from catalog.quality import catalogue_quality_rows
from core.audit import log_audit_event
from core.mixins import StaffRequiredMixin
from growth.models import ProductGrowthData
from inventory.forms import (
    ProductCommerceProfileForm,
    ProductCommercialCoreForm,
    ProductGrowthDataForm,
)
from merchandising.forms import BulkCatalogueEnrichmentForm
from merchandising.models import ProductCommerceProfile
from merchandising.services import apply_bulk_catalogue_enrichment


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
        return {
            "product": product,
            "core_form": core_form,
            "growth_form": growth_form,
            "commerce_form": commerce_form,
            "merchant_missing_fields": missing,
            "merchant_readiness_score": profile.merchant_readiness_score,
            "merchant_ready": not missing,
        }

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

    @staticmethod
    def _is_available(product: Product) -> bool:
        active_variants = [variant for variant in product.variants.all() if variant.is_active]
        if active_variants:
            return any(
                (not variant.track_inventory) or int(variant.stock_quantity) > 0
                for variant in active_variants
            )
        return (not product.track_inventory) or int(product.stock_quantity) > 0

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
            available = self._is_available(product)
            matches_gap = {
                "": True,
                "no_sku": not product.sku.strip(),
                "no_brand": growth is None or not growth.brand.strip(),
                "no_profile": profile is None,
                "no_alt": missing_alt,
                "out_of_stock": product.track_inventory and not available,
                "merchant_not_ready": bool(merchant_missing),
            }.get(gap, True)
            if not matches_gap:
                continue
            rows.append(
                {
                    "product": product,
                    "quality": quality_by_id[product.pk],
                    "brand": growth.brand if growth else "",
                    "condition": growth.get_condition_display() if growth else "",
                    "profile": profile,
                    "merchant_score": profile.merchant_readiness_score if profile else 0,
                    "merchant_missing": merchant_missing,
                    "missing_alt": missing_alt,
                    "available": available,
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
