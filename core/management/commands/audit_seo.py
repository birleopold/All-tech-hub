from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.seo_audit import seo_audit_snapshot


class Command(BaseCommand):
    help = "Audit technical SEO configuration, discovery endpoints and catalogue data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Return a failure status when a critical SEO issue exists.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON instead of a formatted report.",
        )

    def handle(self, *args, **options):
        snapshot = seo_audit_snapshot()
        if options["json"]:
            self.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("SEO readiness"))
            self.stdout.write(f"Score: {snapshot['score']}%")
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_LABEL("Discovery endpoints"))
            for label, url in snapshot["endpoints"].items():
                self.stdout.write(f"- {label}: {url}")
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_LABEL("Catalogue metrics"))
            for label, value in snapshot["metrics"].items():
                self.stdout.write(f"- {label.replace('_', ' ')}: {value}")
            if snapshot["successes"]:
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS("Configured"))
                for message in snapshot["successes"]:
                    self.stdout.write(self.style.SUCCESS(f"- {message}"))
            if snapshot["warnings"]:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("Needs attention"))
                for message in snapshot["warnings"]:
                    self.stdout.write(self.style.WARNING(f"- {message}"))
            if snapshot["critical"]:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR("Critical"))
                for message in snapshot["critical"]:
                    self.stdout.write(self.style.ERROR(f"- {message}"))
        if options["strict"] and snapshot["critical"]:
            raise CommandError("SEO audit found critical issues.")
