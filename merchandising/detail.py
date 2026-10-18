from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from catalog.models import Product
from catalog.strict_seo_detail import StrictSEOProductDetailView
from core.models import CompanySettings
from core.seo import public_url, script_safe_json


class MerchandisedProductDetailView(StrictSEOProductDetailView):
    """Add inspected facts while suppressing legacy assumptions from SEO output."""

    def get_queryset(self):
        return super().get_queryset().select_related("commerce_profile")

    @staticmethod
    def _commerce_profile(product):
        try:
            return product.commerce_profile
        except ObjectDoesNotExist:
            return None

    def _common_product_schema(self, product, review_summary, metadata) -> dict:
        schema = super()._common_product_schema(product, review_summary, metadata)
        profile = self._commerce_profile(product)
        if not profile or not profile.identity_verified_at:
            schema.pop("brand", None)
            schema.pop("gtin", None)
            schema.pop("mpn", None)
        if not profile or not profile.condition_verified_at:
            schema.pop("itemCondition", None)
        return schema

    def _offer_common(self, product, company, growth) -> dict:
        offer = super()._offer_common(product, company, growth)
        if product.kind != Product.KIND_PHYSICAL:
            return offer
        profile = self._commerce_profile(product)
        if profile is None or (
            not profile.merchant_free_shipping
            and profile.merchant_shipping_price is None
        ):
            offer.pop("shippingDetails", None)
            return offer
        shipping_value = 0 if profile.merchant_free_shipping else profile.merchant_shipping_price
        offer["shippingDetails"] = {
            "@type": "OfferShippingDetails",
            "shippingRate": {
                "@type": "MonetaryAmount",
                "value": str(shipping_value or 0),
                "currency": CompanySettings.load().currency_code,
            },
            "shippingDestination": {
                "@type": "DefinedRegion",
                "addressCountry": growth.merchant_country,
            },
        }
        return offer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_card = context["product"]
        source_product = product_card.product
        profile = self._commerce_profile(source_product)
        specifications = profile.specification_pairs if profile else []
        context["commerce_profile"] = profile
        context["commerce_specifications"] = specifications
        if specifications:
            context["commerce_details_json"] = script_safe_json(
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "@id": f"{public_url(source_product.get_absolute_url())}#commercial-details",
                    "name": source_product.name,
                    "url": public_url(source_product.get_absolute_url()),
                    "additionalProperty": [
                        {
                            "@type": "PropertyValue",
                            "name": label,
                            "value": value,
                        }
                        for label, value in specifications
                    ],
                }
            )
        else:
            context["commerce_details_json"] = ""
        return context
