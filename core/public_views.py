from catalog.presentation import prepare_public_products
from core.views import HomeView


class PublicHomeView(HomeView):
    """Homepage with card-ready products prepared from prefetched relations."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_products"] = prepare_public_products(
            context.get("featured_products", [])
        )
        context["featured_services"] = prepare_public_products(
            context.get("featured_services", [])
        )
        return context
