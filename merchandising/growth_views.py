from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Max, Min, Q
from django.urls import reverse
from django.views.generic import TemplateView

from catalog.presentation import prepare_public_products
from catalog.public_views import _annotate_marketplace_values, _available_products_query
from core.models import CompanySettings
from core.seo import meta_description, meta_title, public_url, script_safe_json
from merchandising.constants import commercial_page_path
from merchandising.detail import MerchandisedProductDetailView
from merchandising.models import BuyingGuide, CommercialLandingPage
from merchandising.views import (
    CommercialLandingPageView,
    _published_products,
    _term_query,
)


def catalogue_for_growth_page(page: CommercialLandingPage):
    """Build a live hub catalogue without requiring verified facts twice."""

    queryset = _published_products()
    if page.brand:
        queryset = queryset.filter(
            growth_data__brand__iexact=page.brand.strip(),
            commerce_profile__identity_verified_at__isnull=False,
        )
    if page.condition:
        queryset = queryset.filter(
            growth_data__condition=page.condition.strip().lower(),
            commerce_profile__condition_verified_at__isnull=False,
        )

    category_terms = [
        item.strip() for item in page.category_keywords.split(",") if item.strip()
    ]
    if category_terms:
        category_query = Q()
        for term in category_terms:
            category_query |= (
                Q(category__name__icontains=term)
                | Q(category__parent__name__icontains=term)
                | Q(name__icontains=term)
            )
        queryset = queryset.filter(category_query)

    # Brand and condition are already strong, verified selectors. Applying model
    # keyword presets again can exclude valid products whose exact series was not
    # anticipated when the hub was created.
    search_terms = [
        item.strip() for item in page.search_terms.split(",") if item.strip()
    ]
    # Category terms identify the hub's merchandise. Treat extra search
    # terms as a fallback for hubs without category selectors; requiring both
    # can empty otherwise valid categories (e.g. 'laptops' + 'notebook').
    if search_terms and not page.brand and not page.condition and not category_terms:
        search_query = Q()
        for term in search_terms:
            search_query |= _term_query(term)
        queryset = queryset.filter(search_query)

    return queryset.distinct().order_by("-is_featured", "-updated_at", "name")


class GrowthCommercialLandingPageView(CommercialLandingPageView):
    """Commercial hub with effective variant prices and crawlable pagination."""

    paginate_by = 24

    def get_context_data(self, **kwargs):
        context = TemplateView.get_context_data(self, **kwargs)
        company = CompanySettings.load()
        queryset = _annotate_marketplace_values(catalogue_for_growth_page(self.page))
        paginator = Paginator(queryset, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        products = prepare_public_products(page_obj.object_list)
        price_summary = queryset.aggregate(
            minimum=Min("_effective_price"),
            maximum=Max("_effective_price"),
        )
        available_count = queryset.filter(_available_products_query()).count()
        faqs = list(self.page.faqs.all())
        canonical_path = commercial_page_path(self.page.slug)
        canonical_parameters = (
            {"page": page_obj.number} if page_obj.number > 1 else None
        )
        canonical_url = public_url(canonical_path, canonical_parameters)
        keywords = self.page.keyword_list

        related_guides = BuyingGuide.objects.filter(is_published=True)
        if keywords:
            guide_query = Q()
            for keyword in keywords[:10]:
                guide_query |= (
                    Q(title__icontains=keyword)
                    | Q(excerpt__icontains=keyword)
                    | Q(keywords__icontains=keyword)
                    | Q(related_category_keywords__icontains=keyword)
                )
            related_guides = related_guides.filter(guide_query)
        related_guides = related_guides.order_by("-published_at", "-id")[:4]

        related_pages = CommercialLandingPage.objects.filter(
            is_published=True
        ).exclude(pk=self.page.pk)
        page_query = Q()
        if self.page.brand:
            page_query |= Q(brand__iexact=self.page.brand)
        for keyword in keywords[:8]:
            page_query |= (
                Q(title__icontains=keyword)
                | Q(category_keywords__icontains=keyword)
                | Q(search_terms__icontains=keyword)
            )
        if page_query:
            related_pages = related_pages.filter(page_query)
        related_pages = related_pages.order_by("sort_order", "title")[:8]

        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": self.page.title,
            "url": canonical_url,
            "numberOfItems": paginator.count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": page_obj.start_index() + index,
                    "name": product.name,
                    "url": public_url(product.get_absolute_url()),
                }
                for index, product in enumerate(products)
            ],
        }
        faq_schema = None
        if faqs:
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": faq.question,
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": faq.answer,
                        },
                    }
                    for faq in faqs
                ],
            }
        breadcrumb = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": public_url(reverse("home")),
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": self.page.title,
                    "item": canonical_url,
                },
            ],
        }
        page_suffix = f" – Page {page_obj.number}" if page_obj.number > 1 else ""
        social_image_url = ""
        for product in products:
            image = product.public_display_image
            if image:
                social_image_url = public_url(image.url)
                break

        context.update(
            {
                "commercial_page": self.page,
                "products": products,
                "product_count": paginator.count,
                "available_count": available_count,
                "price_min": price_summary["minimum"],
                "price_max": price_summary["maximum"],
                "faqs": faqs,
                "related_guides": related_guides,
                "related_commercial_pages": related_pages,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": paginator.num_pages > 1,
                "page_title": meta_title(
                    f"{self.page.title}{page_suffix} | {company.company_name}",
                    limit=72,
                ),
                "page_description": meta_description(self.page.meta_description),
                "canonical_url": canonical_url,
                "prev_url": (
                    public_url(
                        canonical_path,
                        {"page": page_obj.previous_page_number()}
                        if page_obj.previous_page_number() > 1
                        else None,
                    )
                    if page_obj.has_previous()
                    else ""
                ),
                "next_url": (
                    public_url(
                        canonical_path,
                        {"page": page_obj.next_page_number()},
                    )
                    if page_obj.has_next()
                    else ""
                ),
                "social_image_url": social_image_url,
                "item_list_json": script_safe_json(item_list),
                "faq_schema_json": (
                    script_safe_json(faq_schema) if faq_schema else ""
                ),
                "breadcrumb_json": script_safe_json(breadcrumb),
            }
        )
        return context


class GrowthProductDetailView(MerchandisedProductDetailView):
    """Connect each product to relevant commercial hubs and expert guidance."""

    @staticmethod
    def _authority_terms(product) -> list[str]:
        raw_terms = [
            product.category.name,
            product.category.parent.name if product.category.parent_id else "",
        ]
        terms = set()
        for raw in raw_terms:
            term = (raw or "").strip()
            if not term:
                continue
            terms.add(term)
            if len(term) > 3 and term.casefold().endswith("s"):
                terms.add(term[:-1])
        return sorted(terms)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        card = context["product"]
        product = card.product
        brand = card.public_brand
        category_terms = self._authority_terms(product)
        authority_query = Q()
        if brand:
            authority_query |= Q(brand__iexact=brand)
            authority_query |= Q(title__icontains=brand)
        for term in category_terms:
            authority_query |= (
                Q(title__icontains=term)
                | Q(category_keywords__icontains=term)
                | Q(search_terms__icontains=term)
            )

        pages = CommercialLandingPage.objects.filter(is_published=True)
        if authority_query:
            pages = pages.filter(authority_query)
        context["product_commercial_pages"] = pages.distinct().order_by(
            "sort_order", "title"
        )[:6]

        guide_query = Q()
        if brand:
            guide_query |= (
                Q(title__icontains=brand)
                | Q(excerpt__icontains=brand)
                | Q(keywords__icontains=brand)
            )
        for term in category_terms:
            guide_query |= (
                Q(title__icontains=term)
                | Q(excerpt__icontains=term)
                | Q(keywords__icontains=term)
                | Q(related_category_keywords__icontains=term)
            )
        guides = BuyingGuide.objects.filter(is_published=True)
        if guide_query:
            guides = guides.filter(guide_query)
        context["product_buying_guides"] = guides.distinct().order_by(
            "-published_at", "-id"
        )[:4]
        return context
