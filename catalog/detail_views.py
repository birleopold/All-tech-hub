from __future__ import annotations

from catalog.presentation import prepare_public_products
from catalog.views import ProductDetailView


class PublicProductDetailView(ProductDetailView):
    """Product detail experience with card-ready values and feed metadata."""

    def get_queryset(self):
        return super().get_queryset().select_related("growth_data")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = prepare_public_products([context["product"]])[0]
        context["product"] = product
        context["recent_products"] = prepare_public_products(
            context.get("recent_products", [])
        )
        context["gallery_count"] = len(
            [image for image in product.gallery_images.all() if image.image]
        ) + (1 if product.image else 0)
        context["rounded_review_rating"] = int(
            round(float(context["review_summary"].get("avg") or 0))
        )
        try:
            context["product_growth_data"] = product.growth_data
        except Exception:
            context["product_growth_data"] = None
        return context
