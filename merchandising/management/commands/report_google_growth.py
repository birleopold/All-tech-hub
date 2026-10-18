"""Read-only Google growth report for the existing LEOSOFT product and SEO stack.

Run from the existing marketing timer or cron once daily; writes one atomic
JSON snapshot and no catalogue, marketing or Google account records.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.core.management.base import BaseCommand, CommandError

from core.seo_audit import seo_audit_snapshot
from merchandising.models import SearchQueryInsight
from merchandising.services import merchant_readiness_snapshot, search_opportunity_rows


def google_growth_report():
    seo = seo_audit_snapshot()
    merchant = merchant_readiness_snapshot(row_limit=0)
    latest = SearchQueryInsight.objects.order_by("-date_end", "-imported_at").first()
    opportunities = search_opportunity_rows(limit=10)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "leosoft-local-audit",
        "note": "These figures are local catalogue/Search Console CSV records, not live Google account metrics.",
        "seo": {
            "score": seo["score"],
            "critical": seo["critical"],
            "warnings": seo["warnings"],
            "metrics": seo["metrics"],
        },
        "merchant": {
            "total_products": merchant["total_products"],
            "ready": merchant["ready"],
            "enabled": merchant["enabled"],
            "enabled_blocked": merchant["enabled_blocked"],
            "blockers": merchant["missing_counts"],
        },
        "search_console": {
            "latest_data_end": latest.date_end.isoformat() if latest and latest.date_end else None,
            "latest_imported_at": latest.imported_at.isoformat() if latest else None,
            "opportunities": [
                {
                    "query": row["insight"].query,
                    "page": row["insight"].page,
                    "impressions": row["insight"].impressions,
                    "clicks": row["insight"].clicks,
                    "position": float(row["insight"].position),
                    "stage": row["stage"],
                }
                for row in opportunities
            ],
        },
    }


class Command(BaseCommand):
    help = "Produce a read-only Google readiness and imported-search-opportunity report."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Write an atomic UTF-8 JSON report at this path.")

    def handle(self, *args, **options):
        report = google_growth_report()
        payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        output = options.get("output")
        if not output:
            self.stdout.write(payload)
            return
        path = Path(output).expanduser()
        if path.suffix.lower() != ".json":
            raise CommandError("Output must end in .json")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement means a reader never sees a half-written report.
        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=".google-growth-", suffix=".json", delete=False
            ) as handle:
                temp_path = Path(handle.name)
                os.chmod(handle.name, 0o600)
                handle.write(payload)
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        self.stdout.write(self.style.SUCCESS(f"Google growth report saved: {path}"))
