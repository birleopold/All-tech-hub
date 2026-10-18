"""Validate the exact staff-approved Google RSS source without touching Google."""
from xml.etree import ElementTree as ET

from django.core.management.base import BaseCommand, CommandError
from django.http import HttpRequest
from django.db import connection

from catalog.seo_feeds import GOOGLE_NS
from merchandising.merchant import approved_google_merchant_feed


class Command(BaseCommand):
    help = (
        "Verify the approved-only Google Merchant XML data source locally. "
        "No Google account, network request, or product modification required."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-items", action="store_true",
            help="Fail when no staff-approved item is eligible for export.",
        )

    def handle(self, *args, **options):
        # A failed guarded release may leave this checkout ahead of the live DB.
        # Report the migration requirement clearly rather than crashing with SQL.
        with connection.cursor() as cursor:
            if "catalog_category" not in connection.introspection.table_names(cursor):
                raise CommandError("Catalogue table is missing. Complete the guarded production deployment before running the feed audit.")
            columns = {column.name for column in connection.introspection.get_table_description(cursor, "catalog_category")}
        if "seo_title" not in columns:
            raise CommandError("Production database has not applied catalog migration 0011 (seo_title missing). Run scripts/final_release_closeout.sh successfully before auditing the Google feed.")
        request = HttpRequest()
        request.method = "GET"
        request.path = "/feeds/google-approved.xml"
        response = approved_google_merchant_feed(request)
        if response.status_code != 200:
            raise CommandError(
                f"Approved Merchant source returned HTTP {response.status_code}"
            )
        if response.get("X-Merchant-Readiness") != "strict":
            raise CommandError("Approved Merchant source is not in strict mode.")

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise CommandError(f"Malformed Merchant XML: {exc}") from exc
        if root.tag != "rss":
            raise CommandError("Approved product source is not an RSS document.")
        channel = root.find("channel")
        if channel is None:
            raise CommandError("Merchant RSS channel is missing.")

        items = channel.findall("item")
        ns = {"g": GOOGLE_NS}
        ids = set()
        required = (
            "id", "title", "description", "link", "image_link",
            "price", "availability", "condition",
        )
        for number, item in enumerate(items, start=1):
            for key in required:
                value = item.findtext(f"g:{key}", default="", namespaces=ns)
                if not value.strip():
                    raise CommandError(
                        f"Merchant item #{number} missing required {key}."
                    )
            item_id = item.findtext("g:id", namespaces=ns)
            if item_id in ids:
                raise CommandError(f"Duplicate Google product id: {item_id}")
            ids.add(item_id)
            link = item.findtext("g:link", namespaces=ns)
            image = item.findtext("g:image_link", namespaces=ns)
            if not link.startswith("https://") or not image.startswith("https://"):
                raise CommandError(
                    f"Merchant item {item_id} must have HTTPS product and image links."
                )
            if item.find("g:shipping/g:price", ns) is None:
                raise CommandError(
                    f"Merchant item {item_id} has no verified shipping price."
                )

        declared = int(response.get("X-Merchant-Eligible-Items", "-1"))
        if declared != len(items):
            raise CommandError("Merchant export count does not match its XML.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Google approved feed valid: {len(items)} products, "
                f"{response.get('X-Merchant-Excluded-Items', '?')} excluded."
            )
        )
        if not items:
            message = (
                "No approved products yet. Review product photos, real stock, "
                "price, identifiers, condition and shipping in the staff catalogue."
            )
            if options["require_items"]:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))
