from django.core.management.base import BaseCommand

from marketing.models import CaptionTemplate


TEMPLATES = [
    {
        "name": "WhatsApp product offer",
        "channel": "whatsapp",
        "body": (
            "{product_name} is available from {company} at {currency} {price}. "
            "View details and enquire here: {url}\n\n{hashtags}"
        ),
        "hashtags": "#LEOSOFT #TechUganda #ComputerDeals",
    },
    {
        "name": "Facebook and Instagram product post",
        "channel": "facebook",
        "body": (
            "Upgrade your technology with {product_name}.\n\n"
            "Category: {category}\nPrice: {currency} {price}\n"
            "Shop or enquire: {url}\n\n{hashtags}"
        ),
        "hashtags": "#LEOSOFT #ComputersUganda #Technology #KampalaBusiness",
    },
    {
        "name": "TikTok product caption",
        "channel": "tiktok",
        "body": (
            "Need a reliable {product_name}? Check the price, specifications and "
            "availability from {company}: {url}\n\n{hashtags}"
        ),
        "hashtags": "#TechTok #UgandaTikTok #LEOSOFT #ComputerTips",
    },
    {
        "name": "LinkedIn business solution",
        "channel": "linkedin",
        "body": (
            "{company} provides {product_name} for organisations and professionals "
            "that need reliable technology and accountable support. Learn more: {url}\n\n"
            "{hashtags}"
        ),
        "hashtags": "#BusinessTechnology #DigitalTransformation #UgandaBusiness",
    },
    {
        "name": "X short product post",
        "channel": "x",
        "body": "{product_name} — {currency} {price}. Details: {url} {hashtags}",
        "hashtags": "#LEOSOFT #TechUganda",
    },
    {
        "name": "Service promotion",
        "channel": "general",
        "body": (
            "Book {product_name} from {company}. Get professional guidance, clear "
            "documentation and dependable follow-up. Start here: {url}\n\n{hashtags}"
        ),
        "hashtags": "#ITServices #LEOSOFT #TechnologySupport",
    },
]


class Command(BaseCommand):
    help = "Create or update LEOSOFT reusable social-media caption templates."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for item in TEMPLATES:
            _, was_created = CaptionTemplate.objects.update_or_create(
                name=item["name"],
                defaults={
                    "channel": item["channel"],
                    "body": item["body"],
                    "hashtags": item["hashtags"],
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Marketing caption templates ready. Created: {created}; updated: {updated}."
            )
        )
