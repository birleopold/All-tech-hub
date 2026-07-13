import json

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from catalog.models import Category, Product, ProductReview, product_review_summary
from core.models import CompanySettings


class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_published=True)
            .select_related("category", "category__parent")
            .prefetch_related("gallery_images", "variants")
            .order_by("category__sort_order", "name")
        )
        kind = self.request.GET.get("kind")
        if kind in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            qs = qs.filter(kind=kind)
        cat = self.request.GET.get("category")
        if cat:
            qs = qs.filter(
                Q(category__slug=cat) | Q(category__parent__slug=cat)
            )
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(short_description__icontains=q)
                | Q(sku__icontains=q)
                | Q(variants__sku__icontains=q)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = (
            Category.objects.filter(parent__isnull=True)
            .prefetch_related("subcategories")
            .order_by("sort_order", "name")
        )
        ctx["current_kind"] = self.request.GET.get("kind") or ""
        ctx["current_category"] = self.request.GET.get("category") or ""
        ctx["search_q"] = self.request.GET.get("q") or ""
        return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "catalog/product_detail.html"
    context_object_name = "product"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(is_published=True)
            .select_related("category")
            .prefetch_related("gallery_images", "variants")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        product = ctx["product"]
        review_summary = product_review_summary(product)
        ctx["review_summary"] = review_summary
        ctx["reviews"] = (
            product.reviews.filter(is_published=True)
            .select_related("customer")
            .order_by("-created_at")[:20]
        )
        ctx["rating_stars"] = range(1, 6)
        ctx["product_schema_json"] = self._product_schema_json(
            product, review_summary
        )
        return ctx

    def _product_schema_json(self, product, review_summary):
        image = product.primary_display_image
        company = CompanySettings.load()
        schema = {
            "@context": "https://schema.org",
            "@type": "Product" if product.kind == Product.KIND_PHYSICAL else "Service",
            "name": product.name,
            "description": product.short_description or product.description,
            "category": product.category.name,
            "url": self.request.build_absolute_uri(product.get_absolute_url()),
        }
        if product.sku:
            schema["sku"] = product.sku
        if image:
            schema["image"] = [self.request.build_absolute_uri(image.url)]
        if review_summary["count"]:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": review_summary["avg"],
                "reviewCount": review_summary["count"],
            }
        if product.kind == Product.KIND_PHYSICAL and product.has_sellable_variants():
            prices = [
                variant.price
                for variant in product.variants.all()
                if variant.is_active and variant.available_to_sell
            ]
            if prices:
                schema["offers"] = {
                    "@type": "AggregateOffer",
                    "priceCurrency": company.currency_code,
                    "lowPrice": str(min(prices)),
                    "highPrice": str(max(prices)),
                    "offerCount": len(prices),
                    "availability": "https://schema.org/InStock",
                }
        else:
            schema["offers"] = {
                "@type": "Offer",
                "priceCurrency": company.currency_code,
                "price": str(product.price),
                "availability": (
                    "https://schema.org/InStock"
                    if product.available_to_sell
                    else "https://schema.org/OutOfStock"
                ),
                "url": self.request.build_absolute_uri(product.get_absolute_url()),
            }
        return mark_safe(json.dumps(schema).replace("</", "<\\/"))


@require_POST
def product_review_submit(request, slug: str):
    product = get_object_or_404(Product, slug=slug, is_published=True)
    name = (request.POST.get("author_name") or "").strip()
    body = (request.POST.get("body") or "").strip()
    try:
        rating = int(request.POST.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5 or not body:
        messages.error(request, "Please rate 1–5 stars and write a short comment.")
        return redirect(product.get_absolute_url())
    customer = None
    if request.user.is_authenticated:
        customer = getattr(request.user, "customer_profile", None)
        if customer and not name:
            name = customer.name
    ProductReview.objects.create(
        product=product,
        customer=customer,
        author_name=name[:120],
        rating=rating,
        body=body[:1000],
        is_published=False,
    )
    messages.success(
        request,
        "Thanks — your review was submitted and will appear once approved.",
    )
    return redirect(product.get_absolute_url())
