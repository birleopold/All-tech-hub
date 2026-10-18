"""Read the daily Google snapshot without exposing raw credentials or files."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from django.conf import settings


def google_dashboard_metrics():
    result = {"state": "missing", "analytics": None, "merchant": None, "queries": []}
    path = Path(settings.BASE_DIR) / "google-reports" / "google-growth-latest.json"
    try:
        if path.stat().st_size > 500000:
            return result
        with path.open(encoding="utf-8") as stream:
            report = json.load(stream)
        updated = datetime.fromisoformat(report["generated_at"])
        if updated.tzinfo is None:
            return result
        result["updated"] = updated
        result["stale"] = datetime.now(timezone.utc) - updated > timedelta(hours=36)
        windsor = report.get("windsor") or {}
        if windsor.get("status") != "queried":
            result["state"] = windsor.get("status", "unavailable")
            return result
        accounts = windsor.get("accounts") or {}
        analytics = accounts.get("analytics") or {}
        if analytics.get("status") == "ok":
            rows = analytics.get("rows") or []
            result["analytics"] = sum(int(row.get("active_users") or 0) for row in rows)
        merchant = accounts.get("merchant") or {}
        if merchant.get("status") == "ok":
            rows = [row for row in (merchant.get("rows") or []) if row.get("product_status_country") == "UG" and row.get("product_status_reporting_context") == "FREE_LISTINGS"]
            result["merchant"] = {
                "active": sum(int(row.get("product_status_active_count") or 0) for row in rows),
                "pending": sum(int(row.get("product_status_pending_count") or 0) for row in rows),
                "disapproved": sum(int(row.get("product_status_disapproved_count") or 0) for row in rows),
            }
        search = accounts.get("search") or {}
        if search.get("status") == "ok":
            result["queries"] = [
                {"query": str(row.get("query") or "")[:140], "page": str(row.get("page") or ""),
                 "clicks": int(row.get("clicks") or 0), "impressions": int(row.get("impressions") or 0),
                 "position": round(float(row.get("position") or 0), 1)}
                for row in (search.get("rows") or [])[:10]
                if str(row.get("page") or "").startswith("https://leosoftug.com/")
            ]
        result["state"] = "ready"
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        result = {"state": "unavailable", "analytics": None, "merchant": None, "queries": []}
    return result
