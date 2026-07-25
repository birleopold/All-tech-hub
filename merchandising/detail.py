from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from catalog.strict_seo_detail import StrictSEOProductDetailView
from core.seo import public_url, script_safe_json


class MerchandisedProductDetailView(StrictSEOProductDetailView):
    """Add inspected specifications, warranty and delivery facts to product pages."""

    def get_queryset(self):
        return super().get_queryset().select_related("commerce_profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_card = context["product"]
        source_product = product_card.product
        try:
            profile = source_product.commerce_profile
        except ObjectDoesNotExist:
            profile = None
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
        if self.request.user.is_staff and profile:
            context["merchant_missing_fields"] = profile.merchant_missing_fields()
        return context
