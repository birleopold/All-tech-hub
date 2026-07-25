from catalog.seo_views import SEOProductListView
from core.public_views import PublicHomeView


class MerchandisedSEOProductListView(SEOProductListView):
    """Keep commerce-profile card signals query-efficient on catalogue pages."""

    def get_queryset(self):
        return super().get_queryset().select_related("commerce_profile")


class MerchandisedHomeView(PublicHomeView):
    """Load inspected product facts for homepage cards without per-card queries."""

    @staticmethod
    def _published_products():
        return PublicHomeView._published_products().select_related("commerce_profile")
