from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from merchandising.models import SearchQueryInsight


ALIASES = {
    "query": ("query", "top queries"),
    "page": ("page", "pages", "landing page"),
    "clicks": ("clicks",),
    "impressions": ("impressions",),
    "ctr": ("ctr",),
    "position": ("position", "average position"),
}


def _normalized(row):
    return {(key or "").strip().lower(): (value or "").strip() for key, value in row.items()}


def _value(row, field):
    for alias in ALIASES[field]:
        if alias in row:
            return row[alias]
    return ""


def _integer(value, field):
    try:
        return int((value or "0").replace(",", "").strip() or 0)
    except ValueError as exc:
        raise CommandError(f"Invalid {field}: {value!r}") from exc


def _decimal(value, field, *, percentage=False):
    cleaned = (value or "0").replace(",", "").strip()
    if cleaned.endswith("%"):
        percentage = True
        cleaned = cleaned[:-1]
    try:
        result = Decimal(cleaned or "0")
    except InvalidOperation as exc:
        raise CommandError(f"Invalid {field}: {value!r}") from exc
    if percentage:
        result = result / Decimal("100")
    return result


class Command(BaseCommand):
    help = "Import a Google Search Console performance CSV into staff query insights."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--date-start", help="Report start date, YYYY-MM-DD.")
        parser.add_argument("--date-end", help="Report end date, YYYY-MM-DD.")
        parser.add_argument("--replace-period", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser()
        if not path.exists():
            raise CommandError(f"CSV file not found: {path}")
        try:
            date_start = date.fromisoformat(options["date_start"]) if options.get("date_start") else None
            date_end = date.fromisoformat(options["date_end"]) if options.get("date_end") else None
        except ValueError as exc:
            raise CommandError("Dates must use YYYY-MM-DD.") from exc

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            self.stdout.write("No rows found.")
            return

        imported = skipped = 0
        with transaction.atomic():
            if options["replace_period"] and (date_start or date_end):
                existing = SearchQueryInsight.objects.all()
                if date_start:
                    existing = existing.filter(date_start=date_start)
                if date_end:
                    existing = existing.filter(date_end=date_end)
                existing.delete()

            for number, source_row in enumerate(rows, start=2):
                row = _normalized(source_row)
                query = _value(row, "query")
                if not query:
                    skipped += 1
                    continue
                try:
                    clicks = _integer(_value(row, "clicks"), "clicks")
                    impressions = _integer(_value(row, "impressions"), "impressions")
                    ctr = _decimal(_value(row, "ctr"), "CTR")
                    position = _decimal(_value(row, "position"), "position")
                except CommandError as exc:
                    raise CommandError(f"Row {number}: {exc}") from exc
                SearchQueryInsight.objects.create(
                    query=query[:500],
                    page=_value(row, "page")[:200],
                    clicks=max(0, clicks),
                    impressions=max(0, impressions),
                    ctr=max(Decimal("0"), ctr),
                    position=max(Decimal("0"), position),
                    date_start=date_start,
                    date_end=date_end,
                )
                imported += 1

            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: imported rows rolled back."))

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} query rows; skipped {skipped}."))
