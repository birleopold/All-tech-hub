from django.core.management.base import BaseCommand

from catalog.models import Product
from merchandising.models import ProductCommerceProfile


class Command(BaseCommand):
    help = "Create missing commercial profiles without changing product or feed data."

    def add_arguments(self, parser):
        parser.add_argument("--published-only", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        queryset = Product.objects.filter(kind=Product.KIND_PHYSICAL).order_by("pk")
        if options["published_only"]:
            queryset = queryset.filter(is_published=True)
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]
        created = existing = 0
        for product in queryset:
            _, was_created = ProductCommerceProfile.objects.get_or_create(product=product)
            if was_created:
                created += 1
            else:
                existing += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Commercial profiles: {created} created, {existing} already existed."
            )
        )
