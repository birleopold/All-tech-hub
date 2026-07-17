import json

from django.core.management.base import BaseCommand, CommandError

from automation.reporting import automation_integrity_findings


class Command(BaseCommand):
    help = "Audit automation heartbeat, locks, terminal records and dead-letter jobs."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        findings = automation_integrity_findings()
        if options["json"]:
            self.stdout.write(json.dumps(findings, default=str, sort_keys=True))
        else:
            self.stdout.write(
                "Automation control audit — "
                f"jobs: {findings['job_count']}; "
                f"runs: {findings['run_count']}; "
                f"dead letters: {findings['dead_letter_jobs']}; "
                f"stale jobs: {findings['stale_running_count']}; "
                f"heartbeat stale: {findings['heartbeat_stale']}; "
                f"integrity errors: {findings['errors']}."
            )
        if options["strict"] and findings["errors"]:
            raise CommandError(
                f"Automation control audit found {findings['errors']} integrity error(s)."
            )
