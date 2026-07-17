from django.core.management.base import BaseCommand, CommandError

from automation.control import AutomationControlError, replay_failed_job
from automation.models import AutomationJob


class Command(BaseCommand):
    help = (
        "Replay one reviewed failed or cancelled email automation job. "
        "Social-post replay remains blocked because external publication may be uncertain."
    )

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument(
            "--confirm",
            required=True,
            help='Exact phrase: "REPLAY <job ID>".',
        )

    def handle(self, *args, **options):
        job_id = int(options["job_id"])
        expected = f"REPLAY {job_id}"
        if (options["confirm"] or "").strip() != expected:
            raise CommandError(f'Confirmation must be exactly: "{expected}".')
        try:
            job = AutomationJob.objects.get(pk=job_id)
        except AutomationJob.DoesNotExist as exc:
            raise CommandError("Automation job does not exist.") from exc
        try:
            replay_failed_job(job, user=None)
        except AutomationControlError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Automation job {job_id} returned to the queue after review."
            )
        )
