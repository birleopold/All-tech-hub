from django.core.management.base import BaseCommand, CommandError

from core.field_encryption import ensure_profile_secret_protected, is_protected_secret
from core.models import StaffTwoFactor


class Command(BaseCommand):
    help = "Encrypt legacy plaintext staff authenticator secrets in place."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count plaintext records without changing them.",
        )

    def handle(self, *args, **options):
        profiles = list(StaffTwoFactor.objects.exclude(secret="").order_by("pk"))
        plaintext = [profile for profile in profiles if not is_protected_secret(profile.secret)]
        if options["dry_run"]:
            self.stdout.write(f"Plaintext TOTP secrets: {len(plaintext)}")
            return

        encrypted = 0
        for profile in plaintext:
            try:
                ensure_profile_secret_protected(profile)
                encrypted += 1
            except Exception as exc:
                raise CommandError(
                    f"Could not encrypt TOTP secret for user_id={profile.user_id}: {exc}"
                ) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Encrypted {encrypted} staff TOTP secret(s).")
        )
