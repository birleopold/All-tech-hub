from __future__ import annotations

import json
from urllib.parse import urlencode

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, IntegerField, Q, Value, When
from django.urls import reverse
from django.utils.safestring import mark_safe

from catalog.models import Product
from catalog.presentation import prepare_public_products
from catalog.views import ProductDetailView


def _script_safe_json(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return mark_safe(
        encoded
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


class PublicProductDetailView(ProductDetailView):
    """Product detail experience with recommendations and card-ready values."""

    def get_queryset(self):
        return super().get_queryset().select_related("growth_data")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        source_product = context["product"]

        try:
            growth_data = source_product.growth_data
        except ObjectDoesNotExist:
            growth_data = None
        brand = (getattr(growth_data, "brand", "") or "").strip()

        related_filter = Q(category_id=source_product.category_id)
        if source_product.category.parent_id:
            related_filter |= Q(
                category__parent_id=source_product.category.parent_id
            )
        if brand:
            related_filter |= Q(growth_data__brand__iexact=brand)

        rank_conditions = [
            When(category_id=source_product.category_id, then=Value(0)),
        ]
        if brand:
            rank_conditions.append(
                When(growth_data__brand__iexact=brand, then=Value(1))
            )

        related_queryset = (
            Product.objects.filter(is_published=True)
            .exclude(pk=source_product.pk)
            .filter(related_filter)
            .select_related("category", "category__parent", "growth_data")
            .prefetch_related("gallery_images", "variants")
            .annotate(
                _related_rank=Case(
                    *rank_conditions,
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("_related_rank", "-is_featured", "name", "pk")[:4]
        )

        product = prepare_public_products([source_product])[0]
        context["product"] = product
        context["related_products"] = prepare_public_products(related_queryset)
        context["recent_products"] = prepare_public_products(
            context.get("recent_products", [])
        )
        context["gallery_count"] = len(
            [image for image in product.gallery_images.all() if image.image]
        ) + (1 if product.image else 0)
        context["rounded_review_rating"] = int(
            round(float(context["review_summary"].get("avg") or 0))
        )
        context["product_growth_data"] = growth_data

        category_url = reverse("product_list")
        category_url = f"{category_url}?{urlencode({'category': source_product.category.slug})}"
        context["product_breadcrumb_json"] = _script_safe_json(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
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
                        "item": self.request.build_absolute_uri(
                            reverse("product_list")
                        ),
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": source_product.category.name,
                        "item": self.request.build_absolute_uri(category_url),
                    },
                    {
                        "@type": "ListItem",
                        "position": 4,
                        "name": source_product.name,
                        "item": self.request.build_absolute_uri(
                            source_product.get_absolute_url()
                        ),
                    },
                ],
            }
        )
        return context
