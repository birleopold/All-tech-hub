import json

from django.core.management.base import BaseCommand, CommandError

from loyalty.reporting import consent_integrity_findings, customer_growth_summary


class Command(BaseCommand):
    help = "Audit marketing consent records and loyalty balance integrity."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument(
            "--channel",
            choices=["email", "whatsapp"],
            default="email",
        )
        parser.add_argument(
            "--topic",
            choices=["product_updates", "special_offers"],
            default="product_updates",
        )
        parser.add_argument(
            "--segment",
            choices=["all", "repeat", "recent", "dormant"],
            default="all",
        )

    def handle(self, *args, **options):
        summary = customer_growth_summary(
            channel=options["channel"],
            topic=options["topic"],
            segment=options["segment"],
        )
        findings = consent_integrity_findings()
        payload = {
            "channel": summary["channel"],
            "topic": summary["topic"],
            "segment": summary["segment"],
            "total_customers": summary["total_customers"],
            "preference_records": summary["preference_records"],
            "email_consent_count": summary["email_consent_count"],
            "whatsapp_consent_count": summary["whatsapp_consent_count"],
            "withdrawn_count": summary["withdrawn_count"],
            "audience_count": summary["audience_count"],
            "loyalty_accounts": summary["loyalty_accounts"],
            "points_balance_total": summary["points_balance_total"],
            "lifetime_points_total": summary["lifetime_points_total"],
            **findings,
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, default=str, sort_keys=True))
        else:
            self.stdout.write(
                "Consent and loyalty audit — "
                f"channel: {payload['channel']}; "
                f"topic: {payload['topic']}; "
                f"customers: {payload['total_customers']}; "
                f"email consent: {payload['email_consent_count']}; "
                f"WhatsApp consent: {payload['whatsapp_consent_count']}; "
                f"audience: {payload['audience_count']}; "
                f"loyalty accounts: {payload['loyalty_accounts']}; "
                f"integrity errors: {payload['errors']}."
            )
        if options["strict"] and payload["errors"]:
            raise CommandError(
                f"Consent and loyalty audit found {payload['errors']} integrity error(s)."
            )
