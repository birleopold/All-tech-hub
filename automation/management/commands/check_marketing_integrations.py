from django.core.management.base import BaseCommand, CommandError

from automation.connectors import ConnectorError, MetaConfig, _graph_request


class Command(BaseCommand):
    help = "Check whether automatic marketing connectors are safely configured."

    def add_arguments(self, parser):
        parser.add_argument(
            "--require-meta",
            action="store_true",
            help="Fail when Facebook or Instagram automatic publishing is unavailable.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Make read-only API calls to verify the configured account IDs and token.",
        )

    def handle(self, *args, **options):
        config = MetaConfig.load()
        facebook = config.supports("facebook")
        instagram = config.supports("instagram")
        self.stdout.write(f"Meta automatic publishing enabled: {config.enabled}")
        self.stdout.write(f"Graph API version: {config.graph_version}")
        self.stdout.write(
            f"Facebook Page connector: {'configured' if facebook else 'not configured'}"
        )
        self.stdout.write(
            f"Instagram Business connector: {'configured' if instagram else 'not configured'}"
        )
        self.stdout.write(
            "WhatsApp Status, TikTok, X, LinkedIn and YouTube: manual publishing"
        )
        if config.enabled and not config.access_token:
            raise CommandError(
                "Meta automatic publishing is enabled but the access token is missing."
            )
        if options["require_meta"] and not (facebook or instagram):
            raise CommandError("No automatic Meta publishing connector is configured.")

        if not options["live"]:
            return
        if not config.enabled or not config.access_token:
            raise CommandError(
                "Enable and configure the Meta connector before running a live check."
            )
        try:
            if facebook:
                page = _graph_request(
                    config,
                    "GET",
                    config.page_id,
                    query={"fields": "id,name"},
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Facebook Page verified: {page.get('name') or page.get('id')}"
                    )
                )
            if instagram:
                account = _graph_request(
                    config,
                    "GET",
                    config.instagram_account_id,
                    query={"fields": "id,username"},
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        "Instagram account verified: "
                        f"{account.get('username') or account.get('id')}"
                    )
                )
        except ConnectorError as exc:
            raise CommandError(
                f"Meta live verification failed: {str(exc)[:500]}"
            ) from exc
