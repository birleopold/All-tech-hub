from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from merchandising.services import merchant_readiness_snapshot


class Command(BaseCommand):
    help = "Audit physical-product readiness for strict Google Merchant publication."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail when a product is Merchant-enabled but still has blocking gaps.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON.",
        )

    def handle(self, *args, **options):
        snapshot = merchant_readiness_snapshot(row_limit=20)
        if options["json"]:
            serializable = {
                key: value
                for key, value in snapshot.items()
                if key != "priority_rows"
            }
            serializable["priority_rows"] = [
                {
                    "product_id": row["product"].pk,
                    "product": row["product"].name,
                    "score": row["score"],
                    "merchant_enabled": row["merchant_enabled"],
                    "missing": row["missing"],
                }
                for row in snapshot["priority_rows"]
            ]
            self.stdout.write(json.dumps(serializable, indent=2, sort_keys=True))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("Merchant readiness"))
            self.stdout.write(
                "Physical products: {total_products} | profiles: {profiles} | "
                "ready: {ready} | enabled: {enabled} | enabled but blocked: "
                "{enabled_blocked} | average: {average_score}%".format(**snapshot)
            )
            self.stdout.write(
                f"Strict feed mode: {'enabled' if snapshot['strict_mode'] else 'disabled'}"
            )
            if snapshot["missing_counts"]:
                self.stdout.write("")
                self.stdout.write(self.style.MIGRATE_LABEL("Most common blockers"))
                for item in snapshot["missing_counts"]:
                    self.stdout.write(f"- {item['label']}: {item['count']}")
            if snapshot["priority_rows"]:
                self.stdout.write("")
                self.stdout.write(self.style.MIGRATE_LABEL("Lowest-readiness products"))
                for row in snapshot["priority_rows"]:
                    missing = ", ".join(row["missing"][:5]) or "none"
                    self.stdout.write(
                        f"- {row['product'].name}: {row['score']}% — {missing}"
                    )

        if options["strict"] and snapshot["enabled_blocked"]:
            raise CommandError(
                f"{snapshot['enabled_blocked']} Merchant-enabled product(s) still have blocking gaps."
            )
