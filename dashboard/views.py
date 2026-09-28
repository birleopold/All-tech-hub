from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import TemplateView

from dashboard.overview import dashboard_overview
from dashboard.snapshot import dashboard_snapshot
from catalog.models import Product
from catalog.quality import catalogue_quality_rows, catalogue_quality_summary
from core.mixins import StaffRequiredMixin
from core.seo_audit import seo_audit_snapshot
from merchandising.forms import SearchConsoleCSVImportForm
from merchandising.services import (
    import_search_console_csv,
    merchant_readiness_snapshot,
    search_opportunity_rows,
)


class StaffDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(dashboard_snapshot(self.request.user))
        ctx.update(dashboard_overview(self.request.user, ctx))
        return ctx


class CatalogueQualityView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/catalogue_quality.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = (
            Product.objects.select_related("category", "growth_data")
            .prefetch_related("gallery_images", "variants")
            .order_by("name", "pk")
        )

        query = (self.request.GET.get("q") or "").strip()
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(sku__icontains=query)
                | Q(category__name__icontains=query)
                | Q(growth_data__brand__icontains=query)
            ).distinct()

        publication = (self.request.GET.get("published") or "").strip()
        if publication == "1":
            products = products.filter(is_published=True)
        elif publication == "0":
            products = products.filter(is_published=False)

        all_rows = catalogue_quality_rows(products)
        status = (self.request.GET.get("status") or "").strip().lower()
        if status in {"ready", "attention", "critical"}:
            visible_rows = [row for row in all_rows if row.status == status]
        else:
            status = ""
            visible_rows = all_rows

        paginator = Paginator(visible_rows, 40)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "quality_rows": page_obj.object_list,
                "quality_summary": catalogue_quality_summary(all_rows),
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": paginator.num_pages > 1,
                "current_query": query,
                "current_status": status,
                "current_publication": publication,
            }
        )
        return context


class SEOControlCenterView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/seo_control_center.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo_audit_snapshot()
        context["merchant"] = merchant_readiness_snapshot(row_limit=10)
        context["search_opportunities"] = search_opportunity_rows(limit=20)
        context["search_console_form"] = kwargs.get(
            "search_console_form", SearchConsoleCSVImportForm()
        )
        return context

    def post(self, request, *args, **kwargs):
        form = SearchConsoleCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = import_search_console_csv(
                    uploaded_file=form.cleaned_data["csv_file"],
                    date_start=form.cleaned_data.get("date_start"),
                    date_end=form.cleaned_data.get("date_end"),
                )
            except ValueError as exc:
                form.add_error("csv_file", str(exc))
            else:
                messages.success(
                    request,
                    (
                        "Search Console data imported: "
                        f"{result['created']} created, {result['updated']} updated and "
                        f"{result['skipped']} skipped."
                    ),
                )
                return redirect("staff_seo")
        messages.error(request, "Correct the Search Console import form.")
        return self.render_to_response(
            self.get_context_data(search_console_form=form)
        )
