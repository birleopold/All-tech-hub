from __future__ import annotations

import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import Category, Product
from catalog.public_views import PublicProductListView
from core.seo import public_base_url, public_url
from growth.models import ProductGrowthData
from merchandising.growth_views import catalogue_for_growth_page
from merchandising.models import BuyingGuide, CommercialLandingPage, DeliveryZone


class Command(BaseCommand):
    help = "Submit changed canonical URLs to IndexNow-supported search engines."

    def add_arguments(self, parser):
        parser.add_argument("urls", nargs="*", help="Canonical paths or absolute URLs.")
        parser.add_argument(
            "--all-products",
            action="store_true",
            help="Include every published product URL.",
        )
        parser.add_argument(
            "--recent-hours",
            type=int,
            help="Include products updated during the previous number of hours.",
        )
        parser.add_argument(
            "--all-indexable",
            action="store_true",
            help=(
                "Include public static, product, category, collection, brand, "
                "commercial and editorial URLs."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the payload without contacting IndexNow.",
        )

    def handle(self, *args, **options):
        key = (getattr(settings, "INDEXNOW_KEY", "") or "").strip()
        enabled = bool(getattr(settings, "INDEXNOW_ENABLED", False))
        if not options["dry_run"] and not enabled:
            raise CommandError("Set ALLTECH_INDEXNOW_ENABLED=1 before live submission.")
        if not key:
            raise CommandError("ALLTECH_INDEXNOW_KEY is required.")

        urls = [public_url(value) for value in options["urls"]]
        products = Product.objects.filter(is_published=True)
        if options["recent_hours"] is not None:
            hours = max(1, options["recent_hours"])
            products = products.filter(
                updated_at__gte=timezone.now() - timedelta(hours=hours)
            )
            urls.extend(public_url(product.get_absolute_url()) for product in products)
        elif options["all_products"]:
            urls.extend(public_url(product.get_absolute_url()) for product in products)

        if options["all_indexable"]:
            urls.extend(
                public_url(reverse(name))
                for name in (
                    "home",
                    "product_list",
                    "physical_product_list",
                    "service_list",
                    "buying_guide",
                    "buying_guide_list",
                    "about",
                    "contact",
                )
            )
            categories = (
                Category.objects.filter(
                    Q(products__is_published=True)
                    | Q(subcategories__products__is_published=True)
                )
                .distinct()
                .order_by("pk")
            )
            urls.extend(
                public_url(reverse("product_category", args=[category.slug]))
                for category in categories
            )
            urls.extend(
                public_url(reverse("product_collection", args=[slug]))
                for slug in PublicProductListView.COLLECTIONS
            )
            brand_values = (
                ProductGrowthData.objects.filter(product__is_published=True)
                .exclude(brand="")
                .values_list("brand", flat=True)
                .distinct()
            )
            urls.extend(
                public_url(reverse("product_brand", args=[slugify(brand)]))
                for brand in brand_values
                if slugify(brand)
            )
            urls.extend(public_url(product.get_absolute_url()) for product in products)

            for page in CommercialLandingPage.objects.filter(is_published=True).order_by(
                "pk"
            ):
                if catalogue_for_growth_page(page).exists():
                    urls.append(public_url(page.get_absolute_url()))
            urls.extend(
                public_url(guide.get_absolute_url())
                for guide in BuyingGuide.objects.filter(is_published=True).order_by("pk")
            )
            if DeliveryZone.objects.filter(is_active=True).exists():
                urls.append(public_url(reverse("delivery_zones")))

        urls = self._validated_urls(urls)
        if not urls:
            raise CommandError("No URLs were selected for submission.")
        if len(urls) > 10000:
            raise CommandError("IndexNow accepts at most 10,000 URLs in one request.")

        host = urlsplit(public_base_url()).netloc
        payload = {
            "host": host,
            "key": key,
            "keyLocation": public_url(reverse("indexnow_key")),
            "urlList": urls,
        }
        if options["dry_run"]:
            self.stdout.write(json.dumps(payload, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Dry run prepared {len(urls)} URLs."))
            return

        request = Request(
            "https://api.indexnow.org/IndexNow",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                status = response.status
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise CommandError(f"IndexNow returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise CommandError(f"IndexNow could not be reached: {exc.reason}") from exc
        if status not in {200, 202}:
            raise CommandError(f"Unexpected IndexNow response: HTTP {status}")
        self.stdout.write(
            self.style.SUCCESS(
                f"IndexNow accepted {len(urls)} canonical URLs (HTTP {status})."
            )
        )

    @staticmethod
    def _validated_urls(values) -> list[str]:
        canonical_host = urlsplit(public_base_url()).netloc.lower()
        result = []
        seen = set()
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.netloc.lower() != canonical_host
            ):
                raise CommandError(f"URL is outside the configured public host: {value}")
            normalized = value.split("#", 1)[0]
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
