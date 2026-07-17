import json

from django.core.management.base import BaseCommand, CommandError

from messaging.deliverability import DeliverabilityError, record_delivery_event
from messaging.models import EmailDeliveryEvent


class Command(BaseCommand):
    help = (
        "Record one reviewed email delivery event from the configured provider. "
        "The provider event ID is idempotent and the raw provider payload is not stored."
    )

    def add_arguments(self, parser):
        parser.add_argument("--event-id", required=True)
        parser.add_argument(
            "--event-type",
            required=True,
            choices=list(dict(EmailDeliveryEvent.TYPE_CHOICES)),
        )
        parser.add_argument("--email", default="")
        parser.add_argument("--tracking-token", default="")
        parser.add_argument("--outbound-email-id", type=int)
        parser.add_argument("--provider", default="")
        parser.add_argument("--provider-message-id", default="")
        parser.add_argument("--occurred-at", default="")
        parser.add_argument("--diagnostic", default="")
        parser.add_argument("--confirm", required=True)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        event_id = (options["event_id"] or "").strip()
        expected = f"RECORD {event_id}"
        if (options["confirm"] or "").strip() != expected:
            raise CommandError(f'Confirmation must be exactly: "{expected}".')
        if not any(
            [
                options.get("email"),
                options.get("tracking_token"),
                options.get("outbound_email_id"),
                options.get("provider_message_id"),
            ]
        ):
            raise CommandError(
                "Identify the message using email, tracking token, outbound ID or provider message ID."
            )

        payload = {
            "event_id": event_id,
            "event_type": options["event_type"],
            "email": options.get("email") or "",
            "tracking_token": options.get("tracking_token") or "",
            "outbound_email_id": options.get("outbound_email_id"),
            "provider": options.get("provider") or "",
            "provider_message_id": options.get("provider_message_id") or "",
            "occurred_at": options.get("occurred_at") or "",
            "metadata": {
                "diagnostic": options.get("diagnostic") or "",
                "ingested_by": "management_command",
            },
        }
        try:
            event, created = record_delivery_event(payload)
        except DeliverabilityError as exc:
            raise CommandError(str(exc)) from exc

        result = {
            "created": created,
            "event_id": event.event_key,
            "event_type": event.event_type,
            "email": event.email_address,
            "outbound_email_id": event.outbound_email_id,
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
        else:
            action = "recorded" if created else "already existed"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Email delivery event {event.event_key} {action}."
                )
            )
