import json

from django.core.management.base import BaseCommand, CommandError

from customer_campaigns.reporting import campaign_integrity_findings


class Command(BaseCommand):
    help = (
        "Audit customer campaign approvals, schedules, consent, delivery evidence "
        "and automation state."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        findings = campaign_integrity_findings()
        if options["json"]:
            self.stdout.write(json.dumps(findings, default=str, sort_keys=True))
        else:
            self.stdout.write(
                "Customer campaign audit — "
                f"campaigns: {findings['campaign_count']}; "
                f"recipients: {findings['recipient_count']}; "
                f"automation events: {findings['automation_event_count']}; "
                f"stale consent: {findings['stale_consent_count']}; "
                f"stale processing: {findings['stale_processing']}; "
                f"overdue schedules: {findings['overdue_schedules']}; "
                f"warnings: {findings['warnings']}; "
                f"integrity errors: {findings['errors']}."
            )
        if options["strict"] and findings["errors"]:
            raise CommandError(
                f"Customer campaign audit found {findings['errors']} integrity error(s)."
            )
