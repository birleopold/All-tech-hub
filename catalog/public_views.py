from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db.models import (
    Case,
    Count,
    DecimalField,
    Exists,
    F,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Q,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Trim
from django.http import JsonResponse
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from catalog.brand_facets import grouped_brand_rows
from catalog.discovery import discovery_seed_for_request, order_for_discovery
from catalog.models import Category, Product, ProductVariant
from catalog.presentation import prepare_public_products
from catalog.views import ProductListView
from core.models import CompanySettings
from growth.models import ProductGrowthData


_SEARCH_SPLIT = re.compile(r"[^\w.+-]+", re.UNICODE)
_PRICE_FIELD = DecimalField(max_digits=12, decimal_places=2)


def _public_catalog_queryset():
    return (
        Product.objects.filter(is_published=True)
        .select_related("category", "category__parent", "growth_data")
        .prefetch_related("gallery_images", "variants")
    )


def _annotate_marketplace_values(queryset):
    active_variants = ProductVariant.objects.filter(
        product_id=OuterRef("pk"),
        is_active=True,
    )
    sellable_variants = active_variants.filter(
        Q(track_inventory=False) | Q(stock_quantity__gt=0)
    )
    return queryset.annotate(
        _has_active_variants=Exists(active_variants),
        _has_sellable_variant=Exists(sellable_variants),
        _effective_price=Coalesce(
            Min(
                "variants__price",
                filter=(
                    Q(variants__is_active=True)
                    & (
                        Q(kind=Product.KIND_SERVICE, variants__price__gt=0)
                        | Q(kind=Product.KIND_PHYSICAL, variants__track_inventory=False)
                        | Q(kind=Product.KIND_PHYSICAL, variants__stock_quantity__gt=0)
                    )
                ),
            ),
            Min("variants__price", filter=Q(variants__is_active=True)),
            F("price"),
            output_field=_PRICE_FIELD,
        ),
    )


def _available_products_query() -> Q:
    return (
        Q(kind=Product.KIND_SERVICE)
        | Q(_has_active_variants=True, _has_sellable_variant=True)
        | Q(_has_active_variants=False, track_inventory=False)
        | Q(_has_active_variants=False, stock_quantity__gt=0)
    )


def _search_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in _SEARCH_SPLIT.split((value or "").strip()):
        cleaned = token.strip()
        if len(cleaned) < 2 or cleaned.lower() in {item.lower() for item in tokens}:
            continue
        tokens.append(cleaned)
        if len(tokens) == 8:
            break
    return tuple(tokens)


def _search_token_query(token: str) -> Q:
    return (
        Q(name__icontains=token)
        | Q(short_description__icontains=token)
        | Q(description__icontains=token)
        | Q(sku__icontains=token)
        | Q(variants__sku__icontains=token)
        | Q(variants__name__icontains=token)
        | Q(category__name__icontains=token)
        | Q(category__parent__name__icontains=token)
        | Q(growth_data__brand__icontains=token)
        | Q(growth_data__mpn__icontains=token)
    )


def _apply_search(queryset, query_text: str):
    for token in _search_tokens(query_text):
        queryset = queryset.filter(_search_token_query(token))
    return queryset


def _search_relevance(query_text: str):
    return Case(
        When(sku__iexact=query_text, then=Value(0)),
        When(name__iexact=query_text, then=Value(1)),
        When(name__istartswith=query_text, then=Value(2)),
        When(growth_data__brand__iexact=query_text, then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )


class PublicProductListView(ProductListView):
    """Marketplace catalogue with accurate pricing, stock and relevant search."""

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
        "business": (
            "business",
            "office",
            "professional",
            "workstation",
            "thinkpad",
            "probook",
            "elitebook",
            "latitude",
        ),
        "student": (
            "student",
            "school",
            "learning",
            "coursework",
            "study",
            "budget",
            "chromebook",
        ),
        "creative": (
            "graphics",
            "design",
            "editing",
            "engineering",
            "cad",
            "creator",
            "precision",
            "workstation",
        ),
        "gaming": ("gaming", "game", "rtx", "gtx", "omen", "legion", "loq", "rog"),
        "home": ("home", "everyday", "personal", "family", "basic"),
    }

    SORT_OPTIONS = {
        "newest": ("-created_at", "-pk"),
        "price_low": ("_effective_price", "name", "pk"),
        "price_high": ("-_effective_price", "name", "pk"),
        "name": ("name", "pk"),
    }

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
            query |= _search_token_query(keyword)
        return query

    def get_queryset(self):
        queryset = _public_catalog_queryset()

        kind = (self.request.GET.get("kind") or "").strip()
        if kind in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            queryset = queryset.filter(kind=kind)

        category = (self.request.GET.get("category") or "").strip()
        if category:
            queryset = queryset.filter(
                Q(category__slug=category) | Q(category__parent__slug=category)
            )

        query_text = (self.request.GET.get("q") or "").strip()
        if query_text:
            queryset = _apply_search(queryset, query_text)

        brand = (self.request.GET.get("brand") or "").strip()
        if brand:
            queryset = queryset.alias(_trimmed_brand=Trim('growth_data__brand')).filter(_trimmed_brand__iexact=brand)

        condition = (self.request.GET.get("condition") or "").strip().lower()
        valid_conditions = {value for value, _ in ProductGrowthData.CONDITION_CHOICES}
        if condition in valid_conditions:
            queryset = queryset.filter(growth_data__condition=condition)

        collection = (self.request.GET.get("collection") or "").strip().lower()
        if collection not in self.COLLECTIONS:
            collection = ""
        if collection == "featured":
            queryset = queryset.filter(is_featured=True)
        elif collection == "deals":
            queryset = queryset.filter(
                Q(compare_at_price__gt=F("price"))
                | Q(variants__compare_at_price__gt=F("variants__price"))
            )
        elif collection == "refurbished":
            queryset = queryset.filter(
                growth_data__condition=ProductGrowthData.CONDITION_REFURBISHED
            )
        elif collection in self.KEYWORD_COLLECTIONS:
            queryset = queryset.filter(
                self._keyword_query(self.KEYWORD_COLLECTIONS[collection])
            )

        queryset = _annotate_marketplace_values(queryset.distinct())

        minimum_price = self._decimal_param(self.request.GET.get("min_price", ""))
        maximum_price = self._decimal_param(self.request.GET.get("max_price", ""))
        if minimum_price is not None:
            queryset = queryset.filter(_effective_price__gte=minimum_price)
        if maximum_price is not None:
            queryset = queryset.filter(_effective_price__lte=maximum_price)

        available_only = (self.request.GET.get("available") or "").strip() in {
            "1",
            "true",
            "yes",
        }
        if available_only or collection == "available":
            queryset = queryset.filter(_available_products_query())

        requested_sort = (self.request.GET.get("sort") or "").strip()
        ordering = self.SORT_OPTIONS.get(requested_sort)
        if ordering:
            self.current_sort = requested_sort
            self.rotation_seed = ""
            return queryset.order_by(*ordering)
        if collection == "new":
            self.current_sort = "newest"
            self.rotation_seed = ""
            return queryset.order_by("-created_at", "-pk")
        if query_text:
            self.current_sort = "relevance"
            self.rotation_seed = ""
            return queryset.annotate(
                _search_rank=_search_relevance(query_text)
            ).order_by("_search_rank", "name", "pk")

        self.current_sort = ""
        self.rotation_seed = discovery_seed_for_request(self.request, "catalog")
        return order_for_discovery(queryset, self.rotation_seed)

    def _remove_filter_url(self, *keys: str) -> str:
        params = self.request.GET.copy()
        for key in (*keys, "page", "view"):
            if key in params:
                del params[key]
        base_url = reverse("product_list")
        encoded = params.urlencode()
        return f"{base_url}?{encoded}" if encoded else base_url

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
            .order_by("-product_count", "brand")
        )
        context["catalog_brands"] = grouped_brand_rows(brand_rows)
        context["condition_choices"] = ProductGrowthData.CONDITION_CHOICES
        context["catalog_collections"] = [
            {"slug": slug, **details} for slug, details in self.COLLECTIONS.items()
        ]

        current_collection = (self.request.GET.get("collection") or "").strip().lower()
        context["current_collection"] = (
            current_collection if current_collection in self.COLLECTIONS else ""
        )
        context["current_collection_details"] = self.COLLECTIONS.get(
            context["current_collection"]
        )
        requested_brand = (self.request.GET.get("brand") or "").strip()
        context["current_brand"] = next(
            (row["brand"] for row in context["catalog_brands"]
             if row["brand"].casefold() == requested_brand.casefold()),
            requested_brand,
        )
        context["current_condition"] = (
            self.request.GET.get("condition") or ""
        ).strip().lower()
        context["current_min_price"] = (
            self.request.GET.get("min_price") or ""
        ).strip()
        context["current_max_price"] = (
            self.request.GET.get("max_price") or ""
        ).strip()
        context["current_available"] = (
            self.request.GET.get("available") or ""
        ).strip() in {"1", "true", "yes"}
        context["catalog_price_range"] = published.filter(
            kind=Product.KIND_PHYSICAL
        ).aggregate(
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
            context.get("catalog_noindex") or context["marketplace_filters_active"]
        )

        active_filters: list[dict[str, str]] = []
        if context.get("search_q"):
            active_filters.append(
                {
                    "label": f'Search: “{context["search_q"]}”',
                    "icon": "bi-search",
                    "remove_url": self._remove_filter_url("q"),
                }
            )
        if context.get("current_kind"):
            active_filters.append(
                {
                    "label": context["current_kind"].title(),
                    "icon": "bi-box-seam",
                    "remove_url": self._remove_filter_url("kind"),
                }
            )
        if selected_category:
            active_filters.append(
                {
                    "label": selected_category.name,
                    "icon": "bi-grid",
                    "remove_url": self._remove_filter_url("category"),
                }
            )
        if context["current_collection_details"]:
            active_filters.append(
                {
                    "label": context["current_collection_details"]["label"],
                    "icon": context["current_collection_details"]["icon"],
                    "remove_url": self._remove_filter_url("collection"),
                }
            )
        if context["current_brand"]:
            active_filters.append(
                {
                    "label": f'Brand: {context["current_brand"]}',
                    "icon": "bi-patch-check",
                    "remove_url": self._remove_filter_url("brand"),
                }
            )
        if context["current_condition"]:
            active_filters.append(
                {
                    "label": f'Condition: {context["current_condition"].title()}',
                    "icon": "bi-box",
                    "remove_url": self._remove_filter_url("condition"),
                }
            )
        if context["current_min_price"] or context["current_max_price"]:
            active_filters.append(
                {
                    "label": "Price range",
                    "icon": "bi-cash-stack",
                    "remove_url": self._remove_filter_url("min_price", "max_price"),
                }
            )
        if context["current_available"]:
            active_filters.append(
                {
                    "label": "Available now",
                    "icon": "bi-check-circle",
                    "remove_url": self._remove_filter_url("available"),
                }
            )
        if context.get("current_sort") and context["current_sort"] not in {
            "",
            "relevance",
        }:
            active_filters.append(
                {
                    "label": "Custom sorting",
                    "icon": "bi-sort-down",
                    "remove_url": self._remove_filter_url("sort"),
                }
            )
        context["active_filter_items"] = active_filters

        if not context["products"]:
            fallback_queryset = _annotate_marketplace_values(
                _public_catalog_queryset().filter(kind=Product.KIND_PHYSICAL)
            ).filter(_available_products_query())
            context["fallback_products"] = prepare_public_products(
                fallback_queryset.order_by("-is_featured", "-updated_at", "name")[:4]
            )
        else:
            context["fallback_products"] = []

        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": (
                context["current_collection_details"]["label"]
                if context["current_collection_details"]
                else "LEOSOFT technology catalogue"
            ),
            "numberOfItems": context["paginator"].count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": context["page_obj"].start_index() + index,
                    "name": product.name,
                    "url": self.request.build_absolute_uri(product.get_absolute_url()),
                }
                for index, product in enumerate(context["products"])
            ],
        }
        context["catalog_item_list_json"] = mark_safe(json.dumps(item_list))

        breadcrumb_items = [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": self.request.build_absolute_uri(reverse("home")),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Catalogue",
                "item": self.request.build_absolute_uri(reverse("product_list")),
            },
        ]
        if selected_category:
            breadcrumb_items.append(
                {
                    "@type": "ListItem",
                    "position": len(breadcrumb_items) + 1,
                    "name": selected_category.name,
                    "item": self.request.build_absolute_uri(
                        f'{reverse("product_list")}?{urlencode({"category": selected_category.slug})}'
                    ),
                }
            )
        elif context["current_collection_details"]:
            breadcrumb_items.append(
                {
                    "@type": "ListItem",
                    "position": len(breadcrumb_items) + 1,
                    "name": context["current_collection_details"]["label"],
                    "item": self.request.build_absolute_uri(
                        f'{reverse("product_list")}?{urlencode({"collection": context["current_collection"]})}'
                    ),
                }
            )
        context["catalog_breadcrumb_json"] = mark_safe(
            json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "BreadcrumbList",
                    "itemListElement": breadcrumb_items,
                }
            )
        )

        canonical_params = {}
        if context.get("current_kind") in (
            Product.KIND_PHYSICAL,
            Product.KIND_SERVICE,
        ):
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


@require_GET
def public_catalog_suggestions(request):
    """Return small, cacheable catalogue suggestions for accessible search UIs."""

    query_text = (request.GET.get("q") or "").strip()
    empty_payload = {
        "query": query_text,
        "products": [],
        "categories": [],
        "brands": [],
        "search_url": reverse("product_list"),
    }
    if len(query_text) < 2:
        return JsonResponse(empty_payload)

    queryset = _apply_search(_public_catalog_queryset(), query_text).distinct()
    queryset = _annotate_marketplace_values(queryset).annotate(
        _search_rank=_search_relevance(query_text)
    ).order_by("_search_rank", "name", "pk")
    products = prepare_public_products(queryset[:6])
    company = CompanySettings.load()

    product_rows = []
    for product in products:
        image_url = ""
        if product.primary_display_image:
            try:
                image_url = product.primary_display_image.url
            except Exception:
                image_url = ""
        product_rows.append(
            {
                "name": product.name,
                "url": product.get_absolute_url(),
                "category": product.category.name,
                "brand": product.public_brand,
                "condition": product.public_condition,
                "kind": product.kind,
                "price": (
                    None
                    if product.kind == Product.KIND_SERVICE and product.public_price <= 0
                    else str(product.public_price)
                ),
                "currency": company.currency_code,
                "available": product.public_available,
                "image": image_url,
            }
        )

    category_query = Q(name__icontains=query_text) | Q(
        description__icontains=query_text
    )
    category_rows = list(
        Category.objects.filter(category_query)
        .annotate(
            direct_count=Count(
                "products",
                filter=Q(products__is_published=True),
                distinct=True,
            ),
            child_count=Count(
                "subcategories__products",
                filter=Q(subcategories__products__is_published=True),
                distinct=True,
            ),
        )
        .annotate(product_count=F("direct_count") + F("child_count"))
        .filter(product_count__gt=0)
        .values("name", "slug", "product_count")
        .order_by("name")[:4]
    )
    categories = [
        {
            "name": row["name"],
            "url": f'{reverse("product_list")}?{urlencode({"category": row["slug"]})}',
            "count": row["product_count"],
        }
        for row in category_rows
    ]

    brand_rows = list(
        ProductGrowthData.objects.filter(
            product__is_published=True,
            brand__icontains=query_text,
        )
        .exclude(brand="")
        .values("brand")
        .annotate(product_count=Count("product_id", distinct=True))
        .order_by("brand")
    )
    brands = [
        {
            "name": row["brand"],
            "url": f'{reverse("product_list")}?{urlencode({"brand": row["brand"]})}',
            "count": row["product_count"],
        }
        for row in grouped_brand_rows(brand_rows, limit=4)
    ]

    payload = {
        "query": query_text,
        "products": product_rows,
        "categories": categories,
        "brands": brands,
        "search_url": f'{reverse("product_list")}?{urlencode({"q": query_text})}',
    }
    response = JsonResponse(payload)
    response["Cache-Control"] = "public, max-age=60"
    return response
