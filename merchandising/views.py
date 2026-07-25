from __future__ import annotations

from django.db.models import Max, Min, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import DetailView, ListView, TemplateView

from catalog.models import Product
from catalog.presentation import prepare_public_products
from core.models import CompanySettings
from core.seo import meta_description, meta_title, public_url, script_safe_json
from merchandising.models import BuyingGuide, CommercialLandingPage, DeliveryZone


ROOT_COMMERCIAL_SLUGS = {
    "laptop-prices-in-uganda",
    "dell-laptops-uganda",
    "hp-laptops-uganda",
    "lenovo-laptops-uganda",
    "macbook-prices-in-uganda",
    "refurbished-laptops-uganda",
    "business-laptops-uganda",
    "student-laptops-uganda",
    "gaming-laptops-uganda",
    "desktop-computer-prices-in-uganda",
    "printer-prices-in-uganda",
    "wifi-router-prices-in-uganda",
}


def commercial_page_path(slug: str) -> str:
    if slug in ROOT_COMMERCIAL_SLUGS:
        return f"/{slug}/"
    return reverse("commercial_landing", kwargs={"slug": slug})


def _published_products():
    return (
        Product.objects.filter(is_published=True, kind=Product.KIND_PHYSICAL)
        .select_related("category", "category__parent", "growth_data", "commerce_profile")
        .prefetch_related("gallery_images", "variants")
    )


def _term_query(term: str) -> Q:
    return (
        Q(name__icontains=term)
        | Q(short_description__icontains=term)
        | Q(description__icontains=term)
        | Q(category__name__icontains=term)
        | Q(category__parent__name__icontains=term)
        | Q(growth_data__brand__icontains=term)
        | Q(commerce_profile__processor_family__icontains=term)
        | Q(commerce_profile__processor_generation__icontains=term)
        | Q(commerce_profile__ram_capacity__icontains=term)
        | Q(commerce_profile__storage_capacity__icontains=term)
        | Q(commerce_profile__graphics__icontains=term)
    )


def _catalogue_for_page(page: CommercialLandingPage):
    queryset = _published_products()
    if page.brand:
        queryset = queryset.filter(growth_data__brand__iexact=page.brand.strip())
    if page.condition:
        queryset = queryset.filter(growth_data__condition=page.condition.strip().lower())

    category_terms = [item.strip() for item in page.category_keywords.split(",") if item.strip()]
    if category_terms:
        category_query = Q()
        for term in category_terms:
            category_query |= (
                Q(category__name__icontains=term)
                | Q(category__parent__name__icontains=term)
                | Q(name__icontains=term)
            )
        queryset = queryset.filter(category_query)

    search_terms = [item.strip() for item in page.search_terms.split(",") if item.strip()]
    if search_terms:
        search_query = Q()
        for term in search_terms:
            search_query |= _term_query(term)
        queryset = queryset.filter(search_query)

    return queryset.distinct().order_by("-is_featured", "-updated_at", "name")


class CommercialLandingPageView(TemplateView):
    template_name = "merchandising/commercial_landing.html"

    def dispatch(self, request, *args, **kwargs):
        self.page = get_object_or_404(
            CommercialLandingPage.objects.prefetch_related("faqs"),
            slug=kwargs["slug"],
            is_published=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = CompanySettings.load()
        queryset = _catalogue_for_page(self.page)
        products = prepare_public_products(queryset[:48])
        price_summary = queryset.aggregate(
            minimum=Min("price"),
            maximum=Max("price"),
        )
        faqs = list(self.page.faqs.all())
        canonical_path = commercial_page_path(self.page.slug)
        canonical_url = public_url(canonical_path)
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

        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": self.page.title,
            "url": canonical_url,
            "numberOfItems": len(products),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": product.name,
                    "url": public_url(product.get_absolute_url()),
                }
                for index, product in enumerate(products, start=1)
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
        context.update(
            {
                "commercial_page": self.page,
                "products": products,
                "product_count": queryset.count(),
                "price_min": price_summary["minimum"],
                "price_max": price_summary["maximum"],
                "faqs": faqs,
                "related_guides": related_guides,
                "page_title": meta_title(f"{self.page.title} | {company.company_name}", limit=72),
                "page_description": meta_description(self.page.meta_description),
                "canonical_url": canonical_url,
                "item_list_json": script_safe_json(item_list),
                "faq_schema_json": script_safe_json(faq_schema) if faq_schema else "",
                "breadcrumb_json": script_safe_json(breadcrumb),
            }
        )
        return context


class BuyingGuideListView(ListView):
    model = BuyingGuide
    template_name = "merchandising/guide_list.html"
    context_object_name = "guides"
    paginate_by = 18

    def get_queryset(self):
        return BuyingGuide.objects.filter(is_published=True).order_by("-published_at", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = CompanySettings.load()
        context.update(
            {
                "page_title": meta_title(f"Technology buying guides | {company.company_name}"),
                "page_description": meta_description(
                    "Practical technology buying, maintenance and procurement guides written and reviewed by the LEOSOFT technical team in Uganda."
                ),
                "canonical_url": public_url(reverse("buying_guide_list")),
            }
        )
        return context


class BuyingGuideDetailView(DetailView):
    model = BuyingGuide
    template_name = "merchandising/guide_detail.html"
    context_object_name = "guide"

    def get_queryset(self):
        return BuyingGuide.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        guide = self.object
        company = CompanySettings.load()
        product_query = Q()
        for keyword in guide.keyword_list[:12]:
            product_query |= _term_query(keyword)
        products = _published_products()
        if product_query:
            products = products.filter(product_query)
        products = prepare_public_products(products.distinct().order_by("-is_featured", "name")[:8])
        related_pages = CommercialLandingPage.objects.filter(is_published=True)
        if guide.keyword_list:
            page_query = Q()
            for keyword in guide.keyword_list[:10]:
                page_query |= (
                    Q(title__icontains=keyword)
                    | Q(category_keywords__icontains=keyword)
                    | Q(search_terms__icontains=keyword)
                    | Q(brand__icontains=keyword)
                )
            related_pages = related_pages.filter(page_query)
        related_pages = related_pages.order_by("sort_order", "title")[:6]
        canonical_url = public_url(guide.get_absolute_url())
        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": guide.title,
            "description": guide.excerpt,
            "datePublished": guide.published_at.isoformat(),
            "dateModified": guide.updated_at.isoformat(),
            "author": {"@type": "Organization", "name": guide.author_name},
            "publisher": {
                "@type": "Organization",
                "name": company.legal_name or company.company_name,
                "url": public_url("/"),
            },
            "mainEntityOfPage": canonical_url,
        }
        context.update(
            {
                "related_products": products,
                "related_commercial_pages": related_pages,
                "page_title": meta_title(f"{guide.title} | {company.company_name}", limit=72),
                "page_description": meta_description(guide.excerpt),
                "canonical_url": canonical_url,
                "article_schema_json": script_safe_json(article_schema),
            }
        )
        return context


class DeliveryZoneListView(TemplateView):
    template_name = "merchandising/delivery_zones.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = CompanySettings.load()
        context.update(
            {
                "zones": DeliveryZone.objects.filter(is_active=True).order_by("sort_order", "name"),
                "page_title": meta_title(f"Technology delivery areas | {company.company_name}"),
                "page_description": meta_description(
                    "Review LEOSOFT delivery areas, indicative charges and collection guidance before ordering technology in Uganda."
                ),
                "canonical_url": public_url(reverse("delivery_zones")),
            }
        )
        return context
