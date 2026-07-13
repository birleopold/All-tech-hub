"""Configure the singleton company profile from the command line."""

from django.core.management.base import BaseCommand

from core.models import CompanySettings


class Command(BaseCommand):
    help = "Create or update the company profile used across the public site and documents."

    def add_arguments(self, parser):
        parser.add_argument("--company-name", required=True)
        parser.add_argument("--legal-name", default="")
        parser.add_argument("--website", default="")
        parser.add_argument("--country", default="")
        parser.add_argument("--currency", default="UGX")
        parser.add_argument("--email", default=None)
        parser.add_argument("--phone", default=None)
        parser.add_argument("--tagline", default=None)

    def handle(self, *args, **options):
        company = CompanySettings.load()
        company.company_name = options["company_name"].strip()
        company.legal_name = options["legal_name"].strip()
        company.website = options["website"].strip()
        company.country = options["country"].strip()
        company.currency_code = options["currency"].strip().upper()

        update_fields = [
            "company_name",
            "legal_name",
            "website",
            "country",
            "currency_code",
        ]
        for option_name, field_name in (
            ("email", "email"),
            ("phone", "phone"),
            ("tagline", "tagline"),
        ):
            value = options[option_name]
            if value is not None:
                setattr(company, field_name, value.strip())
                update_fields.append(field_name)

        company.save(update_fields=update_fields)
        self.stdout.write(
            self.style.SUCCESS(
                f"Company profile configured: {company.legal_name or company.company_name}"
            )
        )
