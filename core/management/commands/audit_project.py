from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.quality import catalogue_quality_rows, catalogue_quality_summary


class Command(BaseCommand):
    help = "Audit production configuration and public catalogue completeness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict-environment",
            action="store_true",
            help="Return a failure status when a production configuration gap is found.",
        )
        parser.add_argument(
            "--fail-on-catalogue-critical",
            action="store_true",
            help="Return a failure status when any catalogue listing scores below 60.",
        )

    def handle(self, *args, **options):
        environment_issues = self._environment_issues()
        self.stdout.write(self.style.MIGRATE_HEADING("Environment"))
        self.stdout.write(
            f"ALLTECH_ENV: {os.getenv('ALLTECH_ENV', 'development')}"
        )
        self.stdout.write(
            f"DJANGO_SETTINGS_MODULE: {os.getenv('DJANGO_SETTINGS_MODULE', '<unset>')}"
        )
        self.stdout.write(f"DEBUG: {settings.DEBUG}")
        self.stdout.write(f"Allowed hosts: {', '.join(settings.ALLOWED_HOSTS) or '<none>'}")
        self.stdout.write(f"Public base URL: {settings.PUBLIC_BASE_URL}")
        if environment_issues:
            for issue in environment_issues:
                self.stdout.write(self.style.WARNING(f"- {issue}"))
        else:
            self.stdout.write(self.style.SUCCESS("Production configuration checks passed."))

        rows = catalogue_quality_rows()
        summary = catalogue_quality_summary(rows)
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Catalogue quality"))
        self.stdout.write(
            "Listings: {total} | average: {average_score}% | ready: {ready} | "
            "attention: {attention} | critical: {critical}".format(**summary)
        )
        for issue in summary["issue_counts"][:10]:
            self.stdout.write(f"- {issue['label']}: {issue['count']}")

        failures = []
        if options["strict_environment"] and environment_issues:
            failures.append("production environment gaps")
        if options["fail_on_catalogue_critical"] and summary["critical"]:
            failures.append(f"{summary['critical']} critical catalogue listings")
        if failures:
            raise CommandError("Audit failed: " + "; ".join(failures))

    @staticmethod
    def _environment_issues() -> list[str]:
        issues: list[str] = []
        production = os.getenv("ALLTECH_ENV", "development").lower() == "production"
        if not production:
            return issues
        if os.getenv("DJANGO_SETTINGS_MODULE") != "config.settings":
            issues.append("DJANGO_SETTINGS_MODULE must be config.settings.")
        if settings.DEBUG:
            issues.append("DEBUG must be disabled.")
        if not settings.ALLOWED_HOSTS:
            issues.append("ALLTECH_ALLOWED_HOSTS is empty.")
        if not settings.CSRF_TRUSTED_ORIGINS:
            issues.append("ALLTECH_CSRF_TRUSTED_ORIGINS is empty.")
        if not settings.PUBLIC_BASE_URL.startswith("https://"):
            issues.append("ALLTECH_PUBLIC_BASE_URL should use HTTPS.")
        static_backend = settings.STORAGES["staticfiles"]["BACKEND"]
        if not static_backend.endswith("ManifestStaticFilesStorage"):
            issues.append("Production static storage is not manifest-backed.")
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            issues.append("Email is still using the console backend.")
        return issues
