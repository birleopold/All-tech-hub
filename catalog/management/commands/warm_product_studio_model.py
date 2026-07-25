from django.core.management.base import BaseCommand, CommandError

from catalog.product_studio import (
    ProductStudioDependencyError,
    studio_model,
    warm_studio_model,
)


class Command(BaseCommand):
    help = "Download and initialise the configured product studio segmentation model."

    def handle(self, *args, **options):
        model_name = studio_model()
        self.stdout.write(f"Preparing product studio model: {model_name}")
        try:
            loaded = warm_studio_model()
        except ProductStudioDependencyError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(
                f"Could not prepare product studio model {model_name}: {exc}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Product studio model ready: {loaded}"))
