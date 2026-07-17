import json

from django.core.management.base import BaseCommand, CommandError

from messaging.reporting import email_deliverability_findings


class Command(BaseCommand):
    help = "Audit the outbound email ledger, delivery timestamps and suppression coverage."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        findings = email_deliverability_findings()
        if options["as_json"]:
            self.stdout.write(json.dumps(findings, sort_keys=True, default=str))
        else:
            self.stdout.write(
                "Email deliverability audit — "
                f"outbound: {findings['outbound_count']}; "
                f"active suppressions: {findings['active_suppressions']}; "
                f"stale queued: {findings['stale_queued']}; "
                f"unprotected bounces: {findings['bounced_without_suppression']}; "
                f"unprotected complaints: {findings['complaints_without_suppression']}; "
                f"integrity errors: {findings['errors']}."
            )
        if options["strict"] and findings["errors"]:
            raise CommandError(
                f"Email deliverability audit found {findings['errors']} integrity error(s)."
            )
