"""Create timestamped database, public-media and private-media backups."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _archive_directory(root: Path, destination_without_suffix: Path) -> Path | None:
    if not root.exists():
        return None
    temporary_base = destination_without_suffix.with_name(
        destination_without_suffix.name + ".partial"
    )
    temporary_zip = Path(
        shutil.make_archive(
            str(temporary_base),
            "zip",
            root_dir=root,
        )
    )
    final_zip = destination_without_suffix.with_suffix(".zip")
    temporary_zip.replace(final_zip)
    return final_zip


class Command(BaseCommand):
    help = (
        "Back up the configured database, public media and protected private media, "
        "then write a checksum manifest."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="",
            help="Backup directory. Defaults to ALLTECH_BACKUP_ROOT or BASE_DIR/backups.",
        )

    def handle(self, *args, **options):
        configured_output = options["output"] or getattr(
            settings,
            "BACKUP_ROOT",
            settings.BASE_DIR / "backups",
        )
        output = Path(configured_output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        database = settings.DATABASES["default"]
        engine = database["ENGINE"]
        created: list[Path] = []

        if engine.endswith("sqlite3"):
            source = Path(database["NAME"])
            if not source.exists():
                raise CommandError(f"SQLite database not found: {source}")
            temporary = output / f"alltech-db-{stamp}.sqlite3.partial"
            target = output / f"alltech-db-{stamp}.sqlite3"
            shutil.copy2(source, temporary)
            temporary.replace(target)
            created.append(target)
        elif engine.endswith("postgresql"):
            temporary = output / f"alltech-db-{stamp}.dump.partial"
            target = output / f"alltech-db-{stamp}.dump"
            command = [
                "pg_dump",
                "--format=custom",
                "--file",
                str(temporary),
                "--dbname",
                database["NAME"],
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
                temporary.unlink(missing_ok=True)
                raise CommandError(f"pg_dump failed: {exc}") from exc
            temporary.replace(target)
            created.append(target)
        else:
            raise CommandError(f"Unsupported database engine: {engine}")

        public_archive = _archive_directory(
            Path(settings.MEDIA_ROOT),
            output / f"alltech-media-{stamp}",
        )
        if public_archive:
            created.append(public_archive)

        private_archive = _archive_directory(
            Path(settings.PRIVATE_MEDIA_ROOT),
            output / f"alltech-private-media-{stamp}",
        )
        if private_archive:
            created.append(private_archive)

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_engine": engine,
            "files": [
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in created
            ],
        }
        manifest_path = output / f"alltech-backup-{stamp}.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Backup created: {manifest_path} ({len(created)} protected artifact(s))."
            )
        )
