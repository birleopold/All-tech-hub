from catalog.presentation import prepare_public_products
from catalog.views import ProductListView


class PublicProductListView(ProductListView):
    """Catalogue list optimized for card rendering without related N+1 queries."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = prepare_public_products(context["products"])
        return context
