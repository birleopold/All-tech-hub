from __future__ import annotations

from urllib.parse import quote, urlencode

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, IntegerField, Q, Value, When
from django.urls import reverse

from catalog.models import Product
from catalog.presentation import prepare_public_products
from catalog.views import ProductDetailView
from core.models import CompanySettings
from core.seo import meta_description, meta_title, public_url, script_safe_json
from growth.models import GrowthSettings
from marketing.models import SocialProfileSettings


class PublicProductDetailView(ProductDetailView):
    """Product detail experience with recommendations and complete SEO signals."""

    def get_queryset(self):
        return super().get_queryset().select_related("growth_data")

    @staticmethod
    def _growth_data(product):
        try:
            return product.growth_data
        except ObjectDoesNotExist:
            return None

    @staticmethod
    def _condition_url(metadata) -> str:
        condition_map = {
            "new": "https://schema.org/NewCondition",
            "refurbished": "https://schema.org/RefurbishedCondition",
            "used": "https://schema.org/UsedCondition",
        }
        return condition_map.get(getattr(metadata, "condition", ""), "")

    @staticmethod
    def _image_urls(product) -> list[str]:
        urls: list[str] = []
        if product.image:
            urls.append(public_url(product.image.url))
        for gallery in product.gallery_images.all():
            if gallery.image:
                url = public_url(gallery.image.url)
                if url not in urls:
                    urls.append(url)
        return urls

    @staticmethod
    def _seller(company) -> dict:
        return {
            "@type": "Organization",
            "@id": f"{public_url('/')}#organization",
            "name": company.legal_name or company.company_name,
            "url": public_url("/"),
        }

    def _offer_common(self, product, company, growth) -> dict:
        offer = {
            "priceCurrency": company.currency_code,
            "url": public_url(product.get_absolute_url()),
            "seller": self._seller(company),
        }
        if product.kind == Product.KIND_PHYSICAL:
            offer["shippingDetails"] = {
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
                offer["hasMerchantReturnPolicy"] = {
                    "@type": "MerchantReturnPolicy",
                    "applicableCountry": growth.merchant_country,
                    "merchantReturnLink": growth.merchant_return_policy_url,
                }
        return offer

    def _common_product_schema(self, product, review_summary, metadata) -> dict:
        schema = {
            "name": product.name,
            "description": meta_description(
                product.short_description or product.description,
                fallback=f"{product.category.name} from LEOSOFT UG LTD.",
                limit=5000,
            ),
            "category": product.category.name,
            "url": public_url(product.get_absolute_url()),
        }
        images = self._image_urls(product)
        if images:
            schema["image"] = images
        if product.sku:
            schema["sku"] = product.sku
        if metadata:
            if metadata.brand:
                schema["brand"] = {"@type": "Brand", "name": metadata.brand}
            if metadata.gtin:
                schema["gtin"] = metadata.gtin
            if metadata.mpn:
                schema["mpn"] = metadata.mpn
            condition = self._condition_url(metadata)
            if condition:
                schema["itemCondition"] = condition
        if review_summary["count"]:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": review_summary["avg"],
                "reviewCount": review_summary["count"],
                "bestRating": 5,
                "worstRating": 1,
            }
        return schema

    def _product_schema_json(self, product, review_summary):
        company = CompanySettings.load()
        growth = GrowthSettings.load()
        metadata = self._growth_data(product)
        common = self._common_product_schema(product, review_summary, metadata)
        offer_common = self._offer_common(product, company, growth)
        active_variants = [variant for variant in product.variants.all() if variant.is_active]

        if product.kind == Product.KIND_PHYSICAL and active_variants:
            variants = []
            images = common.get("image", [])
            for variant in active_variants:
                variant_url = public_url(
                    product.get_absolute_url(),
                    {"variant": variant.pk},
                )
                variant_schema = {
                    "@type": "Product",
                    "name": f"{product.name} — {variant.name}",
                    "description": common["description"],
                    "url": variant_url,
                    "isVariantOf": {"@id": f"{public_url(product.get_absolute_url())}#group"},
                    "additionalProperty": {
                        "@type": "PropertyValue",
                        "name": "Configuration",
                        "value": variant.name,
                    },
                    "offers": {
                        "@type": "Offer",
                        **offer_common,
                        "url": variant_url,
                        "price": str(variant.price),
                        "availability": (
                            "https://schema.org/InStock"
                            if variant.available_to_sell
                            else "https://schema.org/OutOfStock"
                        ),
                    },
                }
                if variant.sku:
                    variant_schema["sku"] = variant.sku
                if images:
                    variant_schema["image"] = images
                if common.get("brand"):
                    variant_schema["brand"] = common["brand"]
                if common.get("itemCondition"):
                    variant_schema["itemCondition"] = common["itemCondition"]
                if metadata and metadata.mpn:
                    variant_schema["mpn"] = metadata.mpn
                variants.append(variant_schema)

            schema = {
                "@context": "https://schema.org",
                "@type": "ProductGroup",
                "@id": f"{public_url(product.get_absolute_url())}#group",
                "productGroupID": product.sku or f"LEOSOFT-{product.pk}",
                **common,
                "hasVariant": variants,
            }
        elif product.kind == Product.KIND_PHYSICAL:
            schema = {
                "@context": "https://schema.org",
                "@type": "Product",
                **common,
                "offers": {
                    "@type": "Offer",
                    **offer_common,
                    "price": str(product.price),
                    "availability": (
                        "https://schema.org/InStock"
                        if product.available_to_sell
                        else "https://schema.org/OutOfStock"
                    ),
                },
            }
        else:
            service_offer = {
                "@type": "Offer",
                **offer_common,
                "availability": "https://schema.org/InStock",
            }
            if product.price > 0:
                service_offer["price"] = str(product.price)
            else:
                # Unknown quotation is not a free service.
                service_offer.pop("priceCurrency", None)
            schema = {
                "@context": "https://schema.org",
                "@type": "Service",
                **common,
                "provider": self._seller(company),
                "areaServed": {
                    "@type": "Country",
                    "name": company.country or "Uganda",
                },
                "offers": service_offer,
            }
        return script_safe_json(schema)

    def _sharing_context(self, product: Product) -> dict:
        company = CompanySettings.load()
        social_settings = SocialProfileSettings.load()
        canonical_url = public_url(product.get_absolute_url())
        image = product.primary_display_image
        social_image_url = public_url(image.url) if image else ""
        raw_description = (
            product.short_description
            or product.description
            or f"{product.category.name} available from {company.company_name}."
        )
        description = meta_description(raw_description)
        title = meta_title(f"{product.name} | {company.company_name}", limit=72)
        share_parts = [
            social_settings.default_share_message.strip(),
            f"{product.name} — {description}",
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
            "whatsapp": "https://wa.me/?text=" + quote(f"{share_text}\n{whatsapp_url}", safe=""),
            "facebook": "https://www.facebook.com/sharer/sharer.php?u=" + quote(facebook_url, safe=""),
            "x": "https://twitter.com/intent/tweet?text=" + quote(share_text, safe="") + "&url=" + quote(x_url, safe=""),
            "linkedin": "https://www.linkedin.com/sharing/share-offsite/?url=" + quote(linkedin_url, safe=""),
            "telegram": "https://t.me/share/url?url=" + quote(telegram_url, safe="") + "&text=" + quote(share_text, safe=""),
            "email": "mailto:?subject=" + quote(title, safe="") + "&body=" + quote(f"{share_text}\n\n{email_url}", safe=""),
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
            "meta_description": description,
            "share_title": title,
            "share_text": share_text,
            "share_links": share_links,
            "social_image_url": social_image_url,
            "copy_share_url": campaign_url("copy-link", "referral"),
            "native_share_url": campaign_url("native-share", "referral"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        source_product = context["product"]
        growth_data = self._growth_data(source_product)
        brand = (getattr(growth_data, "brand", "") or "").strip()

        related_filter = Q(category_id=source_product.category_id)
        if source_product.category.parent_id:
            related_filter |= Q(category__parent_id=source_product.category.parent_id)
        if brand:
            related_filter |= Q(growth_data__brand__iexact=brand)

        rank_conditions = [When(category_id=source_product.category_id, then=Value(0))]
        if brand:
            rank_conditions.append(When(growth_data__brand__iexact=brand, then=Value(1)))

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
        context["recent_products"] = prepare_public_products(context.get("recent_products", []))
        context["gallery_count"] = len(
            [image for image in product.gallery_images.all() if image.image]
        ) + (1 if product.image else 0)
        context["rounded_review_rating"] = int(
            round(float(context["review_summary"].get("avg") or 0))
        )
        context["product_growth_data"] = growth_data

        selected_variant_id = (self.request.GET.get("variant") or "").strip()
        context["selected_variant_id"] = (
            int(selected_variant_id) if selected_variant_id.isdigit() else None
        )

        category_url = public_url(
            reverse("product_category", args=[source_product.category.slug])
        )
        context["product_breadcrumb_json"] = script_safe_json(
            {
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
                        "name": "Catalogue",
                        "item": public_url(reverse("product_list")),
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": source_product.category.name,
                        "item": category_url,
                    },
                    {
                        "@type": "ListItem",
                        "position": 4,
                        "name": source_product.name,
                        "item": public_url(source_product.get_absolute_url()),
                    },
                ],
            }
        )
        return context
