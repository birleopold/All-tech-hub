from __future__ import annotations

from datetime import date
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from merchandising.services import import_search_console_csv


class Command(BaseCommand):
    help = "Import the Queries CSV exported from Google Search Console Performance."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the Search Console Queries CSV.")
        parser.add_argument("--date-start", help="Optional report start date, YYYY-MM-DD.")
        parser.add_argument("--date-end", help="Optional report end date, YYYY-MM-DD.")

    @staticmethod
    def _parse_date(value: str | None, label: str):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError(f"{label} must use YYYY-MM-DD.") from exc

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CommandError(f"CSV file not found: {path}")
        start = self._parse_date(options.get("date_start"), "--date-start")
        end = self._parse_date(options.get("date_end"), "--date-end")
        if start and end and start > end:
            raise CommandError("--date-start cannot be after --date-end.")

        try:
            with path.open("rb") as source:
                result = import_search_console_csv(
                    uploaded_file=File(source, name=path.name),
                    date_start=start,
                    date_end=end,
                )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Search Console import complete: "
                f"{result['created']} created, {result['updated']} updated, "
                f"{result['skipped']} skipped."
            )
        )
