"""Create timestamped database and media backups."""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Back up the configured database and media directory."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="backups")

    def handle(self, *args, **options):
        output = Path(options["output"]).resolve()
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        database = settings.DATABASES["default"]
        engine = database["ENGINE"]

        if engine.endswith("sqlite3"):
            source = Path(database["NAME"])
            if not source.exists():
                raise CommandError(f"SQLite database not found: {source}")
            target = output / f"alltech-db-{stamp}.sqlite3"
            shutil.copy2(source, target)
        elif engine.endswith("postgresql"):
            target = output / f"alltech-db-{stamp}.dump"
            command = [
                "pg_dump", "--format=custom", "--file", str(target),
                "--dbname", database["NAME"],
            ]
            if database.get("HOST"):
                command += ["--host", database["HOST"]]
            if database.get("PORT"):
                command += ["--port", str(database["PORT"])]
            if database.get("USER"):
                command += ["--username", database["USER"]]
            try:
                subprocess.run(command, check=True)
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                raise CommandError(f"pg_dump failed: {exc}") from exc
        else:
            raise CommandError(f"Unsupported database engine: {engine}")

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists():
            shutil.make_archive(
                str(output / f"alltech-media-{stamp}"),
                "zip",
                root_dir=media_root,
            )
        self.stdout.write(self.style.SUCCESS(f"Backup created in {output}"))
