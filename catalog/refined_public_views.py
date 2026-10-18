from __future__ import annotations

import re

from django.db.models import F, Q
from django.urls import reverse
from django.db.models.functions import Trim
from django.utils.safestring import mark_safe

from catalog.discovery import discovery_seed_for_request, order_for_discovery
from catalog.models import Product
from catalog.search_recovery import suggested_catalog_query
from catalog.public_views import (
    PublicProductListView as MarketplaceProductListView,
    _annotate_marketplace_values,
    _available_products_query,
    _public_catalog_queryset,
    _search_relevance,
    _search_token_query,
    public_catalog_suggestions,
)
from growth.models import ProductGrowthData


_SEARCH_SPLIT = re.compile(r"[^\w.+-]+", re.UNICODE)


def _tokens(value: str) -> tuple[str, ...]:
    """Return distinct search tokens, including meaningful one-character terms."""

    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _SEARCH_SPLIT.split((value or "").strip()):
        token = raw.strip()
        key = token.casefold()
        if not token or key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= 8:
            break
    return tuple(tokens)


def _script_safe_json(value) -> str:
    """Keep JSON valid inside a script element even when catalogue text has markup."""

    return mark_safe(
        str(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _delete_parameter(parameters, key: str) -> None:
    if key in parameters:
        del parameters[key]


class RefinedPublicProductListView(MarketplaceProductListView):
    """Validated marketplace search with accurate effective-price ordering."""

    def _sanitize_query_parameters(self) -> None:
        parameters = self.request.GET.copy()

        kind = (parameters.get("kind") or "").strip()
        if kind and kind not in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            _delete_parameter(parameters, "kind")

        condition = (parameters.get("condition") or "").strip().lower()
        valid_conditions = {value for value, _ in ProductGrowthData.CONDITION_CHOICES}
        if condition and condition not in valid_conditions:
            _delete_parameter(parameters, "condition")

        minimum = self._decimal_param(parameters.get("min_price", ""))
        maximum = self._decimal_param(parameters.get("max_price", ""))
        if parameters.get("min_price") and minimum is None:
            _delete_parameter(parameters, "min_price")
        if parameters.get("max_price") and maximum is None:
            _delete_parameter(parameters, "max_price")
        if minimum is not None and maximum is not None and minimum > maximum:
            minimum, maximum = maximum, minimum
            parameters["min_price"] = format(minimum, "f")
            parameters["max_price"] = format(maximum, "f")

        self.request.GET = parameters

    def get_queryset(self):
        self._sanitize_query_parameters()
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
            search_tokens = _tokens(query_text)
            if not search_tokens:
                queryset = queryset.none()
            else:
                for token in search_tokens:
                    queryset = queryset.filter(_search_token_query(token))

        brand = (self.request.GET.get("brand") or "").strip()
        if brand:
            queryset = queryset.alias(_trimmed_brand=Trim('growth_data__brand')).filter(_trimmed_brand__iexact=brand)

        condition = (self.request.GET.get("condition") or "").strip().lower()
        if condition:
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

        minimum = self._decimal_param(self.request.GET.get("min_price", ""))
        maximum = self._decimal_param(self.request.GET.get("max_price", ""))
        if minimum is not None:
            queryset = queryset.filter(_effective_price__gte=minimum)
        if maximum is not None:
            queryset = queryset.filter(_effective_price__lte=maximum)

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
            ).order_by("_search_rank", "-is_featured", "name", "pk")

        self.current_sort = ""
        self.rotation_seed = discovery_seed_for_request(self.request, "catalog")
        return order_for_discovery(queryset, self.rotation_seed)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["catalog_item_list_json"] = _script_safe_json(
            context["catalog_item_list_json"]
        )
        context["catalog_breadcrumb_json"] = _script_safe_json(
            context["catalog_breadcrumb_json"]
        )
        context["search_correction"] = None
        original_query = (self.request.GET.get("q") or "").strip()
        if original_query and context["paginator"].count == 0:
            suggestion = suggested_catalog_query(original_query)
            if suggestion:
                original_params = self.request.GET
                corrected_params = original_params.copy()
                corrected_params["q"] = suggestion
                corrected_params.pop("page", None)
                corrected_params.pop("view", None)
                try:
                    self.request.GET = corrected_params
                    # Reuse the complete filtered queryset so unavailable or
                    # unrelated products are not suggested.
                    exists = self.get_queryset().exists()
                finally:
                    self.request.GET = original_params
                if exists:
                    context["search_correction"] = {
                        "query": suggestion,
                        "url": f'{reverse("product_list")}?{corrected_params.urlencode()}',
                    }
        return context


__all__ = ["RefinedPublicProductListView", "public_catalog_suggestions"]
