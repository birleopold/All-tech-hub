from django.core.management.base import BaseCommand, CommandError

from automation.connectors import MetaConfig


class Command(BaseCommand):
    help = "Check whether automatic marketing connectors are safely configured."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-meta",
            action="store_true",
            help="Fail when Facebook or Instagram automatic publishing is unavailable.",
        )

    def handle(self, *args, **options):
        config = MetaConfig.load()
        facebook = config.supports("facebook")
        instagram = config.supports("instagram")
        self.stdout.write(f"Meta automatic publishing enabled: {config.enabled}")
        self.stdout.write(f"Graph API version: {config.graph_version}")
        self.stdout.write(f"Facebook Page connector: {'configured' if facebook else 'not configured'}")
        self.stdout.write(
            f"Instagram Business connector: {'configured' if instagram else 'not configured'}"
        )
        self.stdout.write(
            "WhatsApp Status, TikTok, X, LinkedIn and YouTube: manual publishing"
        )
        if options["require_meta"] and not (facebook or instagram):
            raise CommandError("No automatic Meta publishing connector is configured.")
        if config.enabled and not config.access_token:
            raise CommandError(
                "Meta automatic publishing is enabled but the Page access token is missing."
            )
