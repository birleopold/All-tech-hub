from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.models import Product


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(is_published=True).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return ["home", "product_list", "buying_guide", "about", "contact"]

    def location(self, item):
        return reverse(item)
