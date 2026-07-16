import json

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product, ProductSerial
from catalog.responsive_images import existing_responsive_sources, responsive_widths
from commerce.models import Order


class Command(BaseCommand):
    help = "Audit catalogue media, customer-facing metadata, order timelines and warranties."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print JSON output.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit unsuccessfully when blocking customer-experience errors exist.",
        )

    def handle(self, *args, **options):
        products = list(
            Product.objects.filter(is_published=True)
            .select_related("category")
            .prefetch_related("gallery_images", "variants")
        )
        missing_images = []
        missing_descriptions = []
        missing_responsive = []
        expected_widths = responsive_widths()

        for product in products:
            image = product.primary_display_image
            if not image:
                missing_images.append(product.pk)
            else:
                available_widths = {
                    width for width, _url in existing_responsive_sources(image)
                }
                try:
                    source_width = int(image.width)
                except Exception:
                    source_width = 0
                required = {
                    width for width in expected_widths if source_width and width <= source_width
                }
                if required - available_widths:
                    missing_responsive.append(
                        {
                            "product_id": product.pk,
                            "missing_widths": sorted(required - available_widths),
                        }
                    )
            if not (product.short_description or product.description).strip():
                missing_descriptions.append(product.pk)

        incomplete_warranties = list(
            ProductSerial.objects.filter(status=ProductSerial.STATUS_SOLD)
            .filter(sold_to__isnull=False)
            .filter(sold_at__isnull=True)
            .values_list("pk", flat=True)
        )
        legacy_orders_without_events = list(
            Order.objects.exclude(status=Order.STATUS_PENDING)
            .filter(status_events__isnull=True)
            .values_list("pk", flat=True)[:100]
        )

        report = {
            "published_products": len(products),
            "missing_primary_images": missing_images,
            "missing_descriptions": missing_descriptions,
            "missing_responsive_derivatives": missing_responsive,
            "sold_serials_missing_sale_date": incomplete_warranties,
            "legacy_orders_without_status_events": legacy_orders_without_events,
            "errors": len(incomplete_warranties),
            "warnings": (
                len(missing_images)
                + len(missing_descriptions)
                + len(missing_responsive)
                + len(legacy_orders_without_events)
            ),
        }

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Published products: {report['published_products']}")
            self.stdout.write(f"Products missing images: {len(missing_images)}")
            self.stdout.write(
                f"Products missing descriptions: {len(missing_descriptions)}"
            )
            self.stdout.write(
                "Products missing responsive derivatives: "
                f"{len(missing_responsive)}"
            )
            self.stdout.write(
                "Sold serials missing sale date: "
                f"{len(incomplete_warranties)}"
            )
            self.stdout.write(
                "Legacy non-pending orders without timeline events: "
                f"{len(legacy_orders_without_events)}"
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Customer experience audit complete — errors: {report['errors']}; "
                    f"warnings: {report['warnings']}."
                )
            )

        if options["strict"] and report["errors"]:
            raise CommandError(
                f"Customer experience audit found {report['errors']} blocking error(s)."
            )
