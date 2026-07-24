from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db.models import Count, F, Max, Min, Q
from django.urls import reverse

from catalog.discovery import discovery_seed_for_request, order_for_discovery
from catalog.models import Category, Product
from catalog.presentation import prepare_public_products
from catalog.views import ProductListView
from growth.models import ProductGrowthData


class PublicProductListView(ProductListView):
    """Marketplace-style catalogue with useful filters and card-ready data."""

    COLLECTIONS = {
        "featured": {
            "label": "Featured picks",
            "description": "Selected products highlighted by the LEOSOFT team.",
            "icon": "bi-stars",
        },
        "deals": {
            "label": "Current deals",
            "description": "Products with a genuine comparison price above the current price.",
            "icon": "bi-tags",
        },
        "new": {
            "label": "New arrivals",
            "description": "The latest products added to the public catalogue.",
            "icon": "bi-lightning-charge",
        },
        "refurbished": {
            "label": "Refurbished technology",
            "description": "Professionally presented refurbished devices and equipment.",
            "icon": "bi-arrow-repeat",
        },
        "available": {
            "label": "Available now",
            "description": "Products currently available to order and services ready to book.",
            "icon": "bi-check-circle",
        },
        "business": {
            "label": "For business",
            "description": "Practical computers and technology for professional work.",
            "icon": "bi-briefcase",
        },
        "student": {
            "label": "For students",
            "description": "Affordable, dependable technology for learning and coursework.",
            "icon": "bi-mortarboard",
        },
        "creative": {
            "label": "Creative and technical work",
            "description": "Options suited to design, engineering, editing and demanding workloads.",
            "icon": "bi-bezier2",
        },
        "gaming": {
            "label": "Gaming and performance",
            "description": "Performance-focused computers and related equipment.",
            "icon": "bi-controller",
        },
        "home": {
            "label": "Home and everyday use",
            "description": "Simple, reliable technology for everyday personal use.",
            "icon": "bi-house-door",
        },
    }

    KEYWORD_COLLECTIONS = {
        "business": ("business", "office", "professional", "workstation", "thinkpad", "probook", "elitebook", "latitude"),
        "student": ("student", "school", "learning", "coursework", "study", "budget", "chromebook"),
        "creative": ("graphics", "design", "editing", "engineering", "cad", "creator", "precision", "workstation"),
        "gaming": ("gaming", "game", "rtx", "gtx", "omen", "legion", "loq", "rog"),
        "home": ("home", "everyday", "personal", "family", "basic"),
    }

    @staticmethod
    def _available_query() -> Q:
        return (
            Q(kind=Product.KIND_SERVICE)
            | Q(track_inventory=False)
            | Q(stock_quantity__gt=0)
            | Q(variants__is_active=True, variants__track_inventory=False)
            | Q(
                variants__is_active=True,
                variants__track_inventory=True,
                variants__stock_quantity__gt=0,
            )
        )

    @staticmethod
    def _decimal_param(value: str) -> Decimal | None:
        try:
            parsed = Decimal((value or "").replace(",", "").strip())
        except (InvalidOperation, AttributeError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _keyword_query(keywords: tuple[str, ...]) -> Q:
        query = Q()
        for keyword in keywords:
            query |= (
                Q(name__icontains=keyword)
                | Q(short_description__icontains=keyword)
                | Q(description__icontains=keyword)
                | Q(category__name__icontains=keyword)
                | Q(category__parent__name__icontains=keyword)
                | Q(growth_data__brand__icontains=keyword)
            )
        return query

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_published=True)
            .select_related("category", "category__parent", "growth_data")
            .prefetch_related("gallery_images", "variants")
        )

        kind = (self.request.GET.get("kind") or "").strip()
        if kind in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            qs = qs.filter(kind=kind)

        category = (self.request.GET.get("category") or "").strip()
        if category:
            qs = qs.filter(
                Q(category__slug=category) | Q(category__parent__slug=category)
            )

        query_text = (self.request.GET.get("q") or "").strip()
        if query_text:
            qs = qs.filter(
                Q(name__icontains=query_text)
                | Q(short_description__icontains=query_text)
                | Q(description__icontains=query_text)
                | Q(sku__icontains=query_text)
                | Q(variants__sku__icontains=query_text)
                | Q(category__name__icontains=query_text)
                | Q(category__parent__name__icontains=query_text)
                | Q(growth_data__brand__icontains=query_text)
            )

        brand = (self.request.GET.get("brand") or "").strip()
        if brand:
            qs = qs.filter(growth_data__brand__iexact=brand)

        condition = (self.request.GET.get("condition") or "").strip().lower()
        valid_conditions = {value for value, _ in ProductGrowthData.CONDITION_CHOICES}
        if condition in valid_conditions:
            qs = qs.filter(growth_data__condition=condition)
        else:
            condition = ""

        minimum_price = self._decimal_param(self.request.GET.get("min_price", ""))
        maximum_price = self._decimal_param(self.request.GET.get("max_price", ""))
        if minimum_price is not None:
            qs = qs.filter(Q(price__gte=minimum_price) | Q(variants__price__gte=minimum_price))
        if maximum_price is not None:
            qs = qs.filter(Q(price__lte=maximum_price) | Q(variants__price__lte=maximum_price))

        available_only = (self.request.GET.get("available") or "").strip() in {"1", "true", "yes"}
        if available_only:
            qs = qs.filter(self._available_query())

        collection = (self.request.GET.get("collection") or "").strip().lower()
        if collection not in self.COLLECTIONS:
            collection = ""
        if collection == "featured":
            qs = qs.filter(is_featured=True)
        elif collection == "deals":
            qs = qs.filter(
                Q(compare_at_price__gt=F("price"))
                | Q(variants__compare_at_price__gt=F("variants__price"))
            )
        elif collection == "refurbished":
            qs = qs.filter(growth_data__condition=ProductGrowthData.CONDITION_REFURBISHED)
        elif collection == "available":
            qs = qs.filter(self._available_query())
        elif collection in self.KEYWORD_COLLECTIONS:
            qs = qs.filter(self._keyword_query(self.KEYWORD_COLLECTIONS[collection]))

        qs = qs.distinct()
        requested_sort = (self.request.GET.get("sort") or "").strip()
        ordering = self.SORT_OPTIONS.get(requested_sort)
        if ordering:
            self.current_sort = requested_sort
            self.rotation_seed = ""
            return qs.order_by(*ordering)
        if collection == "new":
            self.current_sort = "newest"
            self.rotation_seed = ""
            return qs.order_by("-created_at", "-pk")

        self.current_sort = ""
        self.rotation_seed = discovery_seed_for_request(self.request, "catalog")
        return order_for_discovery(qs, self.rotation_seed)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = prepare_public_products(context["products"])

        published = Product.objects.filter(is_published=True)
        brand_rows = (
            ProductGrowthData.objects.filter(
                product__is_published=True,
                brand__gt="",
            )
            .values("brand")
            .annotate(product_count=Count("product_id", distinct=True))
            .order_by("-product_count", "brand")[:18]
        )
        context["catalog_brands"] = list(brand_rows)
        context["condition_choices"] = ProductGrowthData.CONDITION_CHOICES
        context["catalog_collections"] = [
            {"slug": slug, **details} for slug, details in self.COLLECTIONS.items()
        ]

        current_collection = (self.request.GET.get("collection") or "").strip().lower()
        context["current_collection"] = current_collection if current_collection in self.COLLECTIONS else ""
        context["current_collection_details"] = self.COLLECTIONS.get(context["current_collection"])
        context["current_brand"] = (self.request.GET.get("brand") or "").strip()
        context["current_condition"] = (self.request.GET.get("condition") or "").strip().lower()
        context["current_min_price"] = (self.request.GET.get("min_price") or "").strip()
        context["current_max_price"] = (self.request.GET.get("max_price") or "").strip()
        context["current_available"] = (self.request.GET.get("available") or "").strip() in {"1", "true", "yes"}
        context["catalog_price_range"] = published.filter(kind=Product.KIND_PHYSICAL).aggregate(
            minimum=Min("price"),
            maximum=Max("price"),
        )

        current_category = context.get("current_category", "")
        selected_category = None
        if current_category:
            selected_category = (
                Category.objects.filter(slug=current_category)
                .select_related("parent")
                .prefetch_related("subcategories")
                .first()
            )
        context["selected_category"] = selected_category
        context["selected_subcategories"] = (
            list(selected_category.subcategories.all())
            if selected_category and selected_category.parent_id is None
            else []
        )

        filter_params = {
            "collection": context["current_collection"],
            "brand": context["current_brand"],
            "condition": context["current_condition"],
            "min_price": context["current_min_price"],
            "max_price": context["current_max_price"],
            "available": "1" if context["current_available"] else "",
        }
        context["marketplace_filters_active"] = any(filter_params.values())
        context["catalog_noindex"] = bool(
            context.get("catalog_noindex")
            or context["marketplace_filters_active"]
        )

        canonical_params = {}
        if context.get("current_kind") in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            canonical_params["kind"] = context["current_kind"]
        if context.get("current_category"):
            canonical_params["category"] = context["current_category"]
        if context["current_collection"] in {"featured", "new", "refurbished"}:
            canonical_params["collection"] = context["current_collection"]
        page = (self.request.GET.get("page") or "").strip()
        if page.isdigit() and int(page) > 1:
            canonical_params["page"] = page
        canonical = self.request.build_absolute_uri(reverse("product_list"))
        if canonical_params:
            canonical = f"{canonical}?{urlencode(canonical_params)}"
        context["catalog_canonical_url"] = canonical
        return context
