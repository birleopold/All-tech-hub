from django.core.management.base import BaseCommand

from marketing.services import process_due_lead_followups


class Command(BaseCommand):
    help = "Remind enquiry owners and escalate unanswered sales leads to managers."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = process_due_lead_followups(limit=options["limit"], dry_run=options["dry_run"])
        self.stdout.write(f"Reminders: {result['reminded']}; escalations: {result['escalated']}")
