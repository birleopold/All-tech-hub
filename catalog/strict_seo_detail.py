from catalog.detail_views import PublicProductDetailView


class StrictSEOProductDetailView(PublicProductDetailView):
    """Publish only structured offer fields supported by complete stored data."""

    def _offer_common(self, product, company, growth) -> dict:
        offer = super()._offer_common(product, company, growth)
        # A return-policy URL alone is not enough to describe a complete
        # MerchantReturnPolicy. Keep the customer-visible link and Merchant Center
        # configuration, but do not imply an unstored category or return window.
        offer.pop("hasMerchantReturnPolicy", None)
        return offer
