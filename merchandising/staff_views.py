from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from catalog.models import Product
from core.audit import log_audit_event
from core.mixins import StaffRequiredMixin
from growth.models import ProductGrowthData
from inventory.forms import (
    ProductCommerceProfileForm,
    ProductCommercialCoreForm,
    ProductGrowthDataForm,
)
from merchandising.models import ProductCommerceProfile


class ProductCommercialReviewView(StaffRequiredMixin, View):
    template_name = "dashboard/product_commercial_review.html"

    def get_product(self, pk: int) -> Product:
        return get_object_or_404(
            Product.objects.select_related("category", "growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants"),
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
            ProductCommerceProfileForm(data=data, instance=profile, prefix="commerce"),
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

        if all(form.is_valid() for form in forms):
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
