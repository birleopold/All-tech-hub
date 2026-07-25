from __future__ import annotations

from urllib.parse import urlencode

from django.http import Http404
from django.urls import reverse
from django.utils.text import slugify

from catalog.models import Category, Product
from catalog.refined_public_views import RefinedPublicProductListView
from core.models import CompanySettings
from core.seo import meta_description, meta_title, public_url, script_safe_json
from growth.models import ProductGrowthData


class SEOProductListView(RefinedPublicProductListView):
    """Expose valuable catalogue segments through stable, descriptive URLs."""

    def dispatch(self, request, *args, **kwargs):
        parameters = request.GET.copy()
        self.seo_route_kind = (kwargs.get("kind") or "").strip()
        self.seo_category = None
        self.seo_collection = ""
        self.seo_brand = ""

        category_slug = (kwargs.get("category_slug") or "").strip()
        if category_slug:
            self.seo_category = (
                Category.objects.filter(slug=category_slug)
                .select_related("parent")
                .first()
            )
            if self.seo_category is None:
                raise Http404("Category not found")
            parameters["category"] = self.seo_category.slug

        collection_slug = (kwargs.get("collection_slug") or "").strip().lower()
        if collection_slug:
            if collection_slug not in self.COLLECTIONS:
                raise Http404("Collection not found")
            self.seo_collection = collection_slug
            parameters["collection"] = collection_slug

        brand_slug = (kwargs.get("brand_slug") or "").strip().lower()
        if brand_slug:
            brands = (
                ProductGrowthData.objects.filter(product__is_published=True)
                .exclude(brand="")
                .values_list("brand", flat=True)
                .distinct()
            )
            self.seo_brand = next(
                (brand.strip() for brand in brands if slugify(brand) == brand_slug),
                "",
            )
            if not self.seo_brand:
                raise Http404("Brand not found")
            parameters["brand"] = self.seo_brand

        if self.seo_route_kind:
            if self.seo_route_kind not in {Product.KIND_PHYSICAL, Product.KIND_SERVICE}:
                raise Http404("Catalogue type not found")
            parameters["kind"] = self.seo_route_kind

        request.GET = parameters
        return super().dispatch(request, *args, **kwargs)

    def _landing_path(self, context: dict) -> str:
        route_name = getattr(self.request.resolver_match, "url_name", "") or ""
        if route_name == "product_category" and self.seo_category:
            return reverse("product_category", args=[self.seo_category.slug])
        if route_name == "product_collection" and self.seo_collection:
            return reverse("product_collection", args=[self.seo_collection])
        if route_name == "product_brand" and self.seo_brand:
            return reverse("product_brand", args=[slugify(self.seo_brand)])
        if route_name == "physical_product_list":
            return reverse("physical_product_list")
        if route_name == "service_list":
            return reverse("service_list")

        if context.get("selected_category"):
            return reverse("product_category", args=[context["selected_category"].slug])
        if context.get("current_collection") in self.COLLECTIONS:
            return reverse("product_collection", args=[context["current_collection"]])
        if context.get("current_brand"):
            return reverse("product_brand", args=[slugify(context["current_brand"])])
        if context.get("current_kind") == Product.KIND_PHYSICAL:
            return reverse("physical_product_list")
        if context.get("current_kind") == Product.KIND_SERVICE:
            return reverse("service_list")
        return reverse("product_list")

    def _page_copy(self, context: dict) -> dict[str, str]:
        company = CompanySettings.load()
        selected_category = context.get("selected_category")
        collection = context.get("current_collection_details")
        brand = context.get("current_brand")
        kind = context.get("current_kind")

        if selected_category:
            subject = selected_category.name
            title = f"{subject} in Uganda | {company.company_name}"
            description = selected_category.description or (
                f"Browse {subject.lower()} available from {company.company_name}. "
                "Compare prices, condition, specifications and availability, then request support or a formal quotation."
            )
            heading = f"Shop {subject} with clear product details"
            intro = selected_category.description or (
                f"Compare available {subject.lower()} by specification, condition, price and stock before making a decision."
            )
            eyebrow = "Technology category"
        elif collection:
            subject = collection["label"]
            title = f"{subject} in Uganda | {company.company_name}"
            description = collection["description"]
            heading = subject
            intro = collection["description"]
            eyebrow = "Curated technology collection"
        elif brand:
            subject = brand
            title = f"{brand} computers and technology in Uganda | {company.company_name}"
            description = (
                f"Browse available {brand} computers and technology from {company.company_name}. "
                "Compare specifications, condition, price and stock, and request a formal quotation."
            )
            heading = f"Explore {brand} technology"
            intro = (
                f"Compare available {brand} products by configuration, condition, price and current availability."
            )
            eyebrow = "Shop by brand"
        elif kind == Product.KIND_SERVICE:
            title = f"Computer repairs and IT services in Uganda | {company.company_name}"
            description = (
                f"Book computer diagnostics, repairs, installation, networking and business IT support from {company.company_name}."
            )
            heading = "Book skilled technology support"
            intro = (
                "Explore repairs, installations and IT support with clear starting prices and a professional service process."
            )
            eyebrow = "Professional IT services"
        elif kind == Product.KIND_PHYSICAL:
            title = f"Computers and technology products in Uganda | {company.company_name}"
            description = (
                f"Shop laptops, desktops, accessories and technology products from {company.company_name}. "
                "Compare specifications, price, condition and availability."
            )
            heading = "Find technology that fits the job"
            intro = "Narrow the catalogue by category, brand, condition, budget and current availability."
            eyebrow = "Computers and technology products"
        else:
            title = f"Technology catalogue in Uganda | {company.company_name}"
            description = (
                f"Browse computers, accessories, repairs and professional IT services from {company.company_name}. "
                "Search, filter and compare dependable options."
            )
            heading = "Search, filter and compare with confidence"
            intro = "Search products and services from one organised technology catalogue."
            eyebrow = "Products and professional services"

        page_number = context["page_obj"].number
        if page_number > 1:
            title = f"{title} – Page {page_number}"
            heading = f"{heading} – Page {page_number}"
        return {
            "title": meta_title(title, limit=72),
            "description": meta_description(description),
            "heading": heading,
            "intro": intro,
            "eyebrow": eyebrow,
        }

    def _pagination_url(self, landing_path: str, page_number: int) -> str:
        parameters = self.request.GET.copy()
        parameters.pop("view", None)
        if page_number <= 1:
            parameters.pop("page", None)
        else:
            parameters["page"] = str(page_number)
        encoded = parameters.urlencode()
        return public_url(f"{landing_path}?{encoded}" if encoded else landing_path)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        landing_path = self._landing_path(context)
        page_number = context["page_obj"].number
        canonical_query = {"page": page_number} if page_number > 1 else None
        canonical_url = public_url(landing_path, canonical_query)

        route_keys = {"category", "collection", "brand", "kind", "page"}
        active_keys = {
            key
            for key, value in self.request.GET.items()
            if value and key not in {"view"}
        }
        extra_filters = active_keys - route_keys
        indexable_landing = not bool(extra_filters)
        if context.get("search_q") or context.get("current_sort") not in {"", "relevance"}:
            indexable_landing = False
        if context.get("current_min_price") or context.get("current_max_price"):
            indexable_landing = False
        if context.get("current_condition") or context.get("current_available"):
            indexable_landing = False

        copy = self._page_copy(context)
        social_image = ""
        for product in context.get("products", []):
            image = getattr(product, "public_display_image", None) or getattr(
                product, "primary_display_image", None
            )
            if image:
                try:
                    social_image = public_url(image.url)
                except Exception:
                    social_image = ""
                if social_image:
                    break

        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": copy["heading"],
            "url": canonical_url,
            "numberOfItems": context["paginator"].count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": context["page_obj"].start_index() + index,
                    "name": product.name,
                    "url": public_url(product.get_absolute_url()),
                }
                for index, product in enumerate(context.get("products", []))
            ],
        }
        breadcrumb_items = [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": public_url(reverse("home")),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Catalogue",
                "item": public_url(reverse("product_list")),
            },
        ]
        if landing_path != reverse("product_list"):
            breadcrumb_items.append(
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": copy["heading"],
                    "item": canonical_url,
                }
            )

        context.update(
            {
                "catalog_page_title": copy["title"],
                "catalog_meta_description": copy["description"],
                "catalog_heading": copy["heading"],
                "catalog_intro": copy["intro"],
                "catalog_eyebrow": copy["eyebrow"],
                "catalog_canonical_url": canonical_url,
                "catalog_noindex": not indexable_landing,
                "catalog_social_image_url": social_image,
                "catalog_item_list_json": script_safe_json(item_list),
                "catalog_breadcrumb_json": script_safe_json(
                    {
                        "@context": "https://schema.org",
                        "@type": "BreadcrumbList",
                        "itemListElement": breadcrumb_items,
                    }
                ),
                "catalog_prev_url": (
                    self._pagination_url(landing_path, page_number - 1)
                    if context["page_obj"].has_previous()
                    else ""
                ),
                "catalog_next_url": (
                    self._pagination_url(landing_path, page_number + 1)
                    if context["page_obj"].has_next()
                    else ""
                ),
            }
        )
        return context
