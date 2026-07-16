import json
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from catalog.discovery import discovery_seed_for_request, order_for_discovery
from catalog.experience import (
    clear_comparison,
    compare_ids,
    compared_products,
    product_is_compared,
    recent_products,
    record_recent_product,
    toggle_compared_product,
)
from catalog.models import Category, Product, ProductReview, product_review_summary
from core.models import CompanySettings
from growth.models import GrowthSettings
from marketing.models import SocialProfileSettings


class ProductListView(ListView):
    model = Product
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    SORT_OPTIONS = {
        "newest": ("-created_at", "-pk"),
        "price_low": ("price", "name", "pk"),
        "price_high": ("-price", "name", "pk"),
        "name": ("name", "pk"),
    }

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_published=True)
            .select_related("category", "category__parent")
            .prefetch_related("gallery_images", "variants")
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

        requested_sort = (self.request.GET.get("sort") or "").strip()
        ordering = self.SORT_OPTIONS.get(requested_sort)
        if ordering:
            self.current_sort = requested_sort
            self.rotation_seed = ""
            return qs.order_by(*ordering)

        self.current_sort = ""
        self.rotation_seed = discovery_seed_for_request(self.request, "catalog")
        return order_for_discovery(qs, self.rotation_seed)

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
        ctx["current_sort"] = getattr(self, "current_sort", "")
        ctx["rotation_seed"] = getattr(self, "rotation_seed", "")
        ctx["compare_product_ids"] = compare_ids(self.request)
        ctx["compare_count"] = len(ctx["compare_product_ids"])

        canonical_params = {}
        if ctx["current_kind"] in (Product.KIND_PHYSICAL, Product.KIND_SERVICE):
            canonical_params["kind"] = ctx["current_kind"]
        if ctx["current_category"]:
            canonical_params["category"] = ctx["current_category"]
        page = (self.request.GET.get("page") or "").strip()
        if page.isdigit() and int(page) > 1:
            canonical_params["page"] = page
        canonical = self.request.build_absolute_uri(reverse("product_list"))
        if canonical_params:
            canonical = f"{canonical}?{urlencode(canonical_params)}"
        ctx["catalog_canonical_url"] = canonical
        ctx["catalog_noindex"] = bool(ctx["search_q"] or ctx["current_sort"])
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
            .select_related("category", "category__parent")
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
        ctx["recent_products"] = recent_products(
            self.request,
            exclude_id=product.pk,
            limit=4,
        )
        ctx["is_in_compare"] = product_is_compared(self.request, product.pk)
        ctx["compare_count"] = len(compare_ids(self.request))
        ctx.update(self._sharing_context(product))
        record_recent_product(self.request, product)
        return ctx

    def _sharing_context(self, product: Product) -> dict:
        company = CompanySettings.load()
        social_settings = SocialProfileSettings.load()
        canonical_url = self.request.build_absolute_uri(product.get_absolute_url())
        image = product.primary_display_image
        social_image_url = (
            self.request.build_absolute_uri(image.url) if image else ""
        )

        raw_description = (
            product.short_description
            or product.description
            or f"{product.category.name} available from {company.company_name}."
        )
        meta_description = " ".join(raw_description.split())[:160]
        share_title = f"{product.name} | {company.company_name}"
        share_parts = [
            social_settings.default_share_message.strip(),
            f"{product.name} — {meta_description}",
        ]
        share_text = " ".join(part for part in share_parts if part).strip()

        def campaign_url(source: str, medium: str = "social") -> str:
            params = urlencode(
                {
                    "utm_source": source,
                    "utm_medium": medium,
                    "utm_campaign": "product_service_share",
                    "utm_content": product.slug,
                }
            )
            return f"{canonical_url}?{params}"

        whatsapp_url = campaign_url("whatsapp")
        facebook_url = campaign_url("facebook")
        x_url = campaign_url("x")
        linkedin_url = campaign_url("linkedin")
        telegram_url = campaign_url("telegram")
        pinterest_url = campaign_url("pinterest")
        email_url = campaign_url("email", "referral")

        share_links = {
            "whatsapp": (
                "https://wa.me/?text="
                + quote(f"{share_text}\n{whatsapp_url}", safe="")
            ),
            "facebook": (
                "https://www.facebook.com/sharer/sharer.php?u="
                + quote(facebook_url, safe="")
            ),
            "x": (
                "https://twitter.com/intent/tweet?text="
                + quote(share_text, safe="")
                + "&url="
                + quote(x_url, safe="")
            ),
            "linkedin": (
                "https://www.linkedin.com/sharing/share-offsite/?url="
                + quote(linkedin_url, safe="")
            ),
            "telegram": (
                "https://t.me/share/url?url="
                + quote(telegram_url, safe="")
                + "&text="
                + quote(share_text, safe="")
            ),
            "email": (
                "mailto:?subject="
                + quote(share_title, safe="")
                + "&body="
                + quote(f"{share_text}\n\n{email_url}", safe="")
            ),
            "pinterest": "",
        }
        if social_image_url:
            share_links["pinterest"] = (
                "https://pinterest.com/pin/create/button/?url="
                + quote(pinterest_url, safe="")
                + "&media="
                + quote(social_image_url, safe="")
                + "&description="
                + quote(share_text, safe="")
            )

        return {
            "canonical_url": canonical_url,
            "meta_description": meta_description,
            "share_title": share_title,
            "share_text": share_text,
            "share_links": share_links,
            "social_image_url": social_image_url,
            "copy_share_url": campaign_url("copy-link", "referral"),
            "native_share_url": campaign_url("native-share", "referral"),
        }

    def _product_schema_json(self, product, review_summary):
        company = CompanySettings.load()
        growth = GrowthSettings.load()
        try:
            metadata = product.growth_data
        except Exception:
            metadata = None

        schema_type = "Product" if product.kind == Product.KIND_PHYSICAL else "Service"
        schema = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "name": product.name,
            "description": product.short_description or product.description,
            "category": product.category.name,
            "url": self.request.build_absolute_uri(product.get_absolute_url()),
        }
        if product.sku:
            schema["sku"] = product.sku

        image_urls = []
        if product.image:
            image_urls.append(self.request.build_absolute_uri(product.image.url))
        for gallery in product.gallery_images.all():
            if gallery.image:
                url = self.request.build_absolute_uri(gallery.image.url)
                if url not in image_urls:
                    image_urls.append(url)
        if image_urls:
            schema["image"] = image_urls

        if metadata:
            if metadata.brand:
                schema["brand"] = {"@type": "Brand", "name": metadata.brand}
            if metadata.gtin:
                schema["gtin"] = metadata.gtin
            if metadata.mpn:
                schema["mpn"] = metadata.mpn
            condition_map = {
                "new": "https://schema.org/NewCondition",
                "refurbished": "https://schema.org/RefurbishedCondition",
                "used": "https://schema.org/UsedCondition",
            }
            if metadata.condition in condition_map:
                schema["itemCondition"] = condition_map[metadata.condition]

        if review_summary["count"]:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": review_summary["avg"],
                "reviewCount": review_summary["count"],
            }

        seller = {
            "@type": "Organization",
            "name": company.company_name,
            "url": company.website or self.request.build_absolute_uri(reverse("home")),
        }
        offer_common = {
            "priceCurrency": company.currency_code,
            "url": self.request.build_absolute_uri(product.get_absolute_url()),
            "seller": seller,
        }
        if product.kind == Product.KIND_PHYSICAL:
            offer_common["shippingDetails"] = {
                "@type": "OfferShippingDetails",
                "shippingRate": {
                    "@type": "MonetaryAmount",
                    "value": str(growth.merchant_shipping_price),
                    "currency": company.currency_code,
                },
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": growth.merchant_country,
                },
            }
            if growth.merchant_return_policy_url:
                offer_common["hasMerchantReturnPolicy"] = {
                    "@type": "MerchantReturnPolicy",
                    "applicableCountry": growth.merchant_country,
                    "url": growth.merchant_return_policy_url,
                }

        if product.kind == Product.KIND_PHYSICAL and product.has_sellable_variants():
            variants = [
                variant
                for variant in product.variants.all()
                if variant.is_active
            ]
            prices = [variant.price for variant in variants if variant.available_to_sell]
            if prices:
                schema["offers"] = {
                    "@type": "AggregateOffer",
                    **offer_common,
                    "lowPrice": str(min(prices)),
                    "highPrice": str(max(prices)),
                    "offerCount": len(prices),
                    "availability": "https://schema.org/InStock",
                }
            else:
                schema["offers"] = {
                    "@type": "Offer",
                    **offer_common,
                    "price": str(product.min_active_variant_price or product.price),
                    "availability": "https://schema.org/OutOfStock",
                }
        else:
            schema["offers"] = {
                "@type": "Offer",
                **offer_common,
                "price": str(product.price),
                "availability": (
                    "https://schema.org/InStock"
                    if product.available_to_sell
                    else "https://schema.org/OutOfStock"
                ),
            }
        if product.kind == Product.KIND_SERVICE:
            schema["provider"] = seller
        return mark_safe(json.dumps(schema).replace("</", "<\\/"))


@require_POST
def product_compare_toggle(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id, is_published=True)
    added, message = toggle_compared_product(request, product)
    if added:
        messages.success(request, message)
    elif product.pk in compare_ids(request):
        messages.warning(request, message)
    else:
        messages.info(request, message)
    next_url = request.POST.get("next") or product.get_absolute_url()
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = product.get_absolute_url()
    return redirect(next_url)


def product_compare(request):
    products = compared_products(request)
    return render(
        request,
        "catalog/product_compare.html",
        {
            "products": products,
            "compare_count": len(products),
        },
    )


@require_POST
def product_compare_clear(request):
    clear_comparison(request)
    messages.info(request, "Product comparison cleared.")
    return redirect("product_compare")


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
