"""Verify backup checksums and archive readability without restoring production."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.backups import latest_backup_status


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Verify a LEOSOFT backup manifest, checksums, ZIP archives and DB dump readability."

    def add_arguments(self, parser):
        parser.add_argument(
            "manifest",
            nargs="?",
            default="",
            help="Manifest path. Defaults to the newest manifest in BACKUP_ROOT.",
        )

    def handle(self, *args, **options):
        backup_root = Path(
            getattr(settings, "BACKUP_ROOT", settings.BASE_DIR / "backups")
        ).resolve()
        if options["manifest"]:
            manifest_path = Path(options["manifest"]).resolve()
        else:
            backup = latest_backup_status(backup_root)
            if not backup.exists or backup.path is None:
                raise CommandError(f"No backup manifest found in {backup_root}.")
            manifest_path = (
                backup.path
                if backup.path.is_file()
                else backup.path / "manifest.json"
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read backup manifest: {exc}") from exc

        failures: list[str] = []
        for item in manifest.get("files", []):
            path = manifest_path.parent / item["name"]
            if not path.exists():
                failures.append(f"Missing: {path.name}")
                continue
            if path.stat().st_size != int(item.get("size_bytes", -1)):
                failures.append(f"Size mismatch: {path.name}")
                continue
            if _sha256(path) != item.get("sha256"):
                failures.append(f"Checksum mismatch: {path.name}")
                continue

            if path.suffix == ".zip":
                try:
                    with zipfile.ZipFile(path, "r") as archive:
                        bad_member = archive.testzip()
                    if bad_member:
                        failures.append(f"Corrupt ZIP member in {path.name}: {bad_member}")
                except (OSError, zipfile.BadZipFile) as exc:
                    failures.append(f"Unreadable ZIP {path.name}: {exc}")
            elif path.suffix == ".dump":
                try:
                    subprocess.run(
                        ["pg_restore", "--list", str(path)],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except FileNotFoundError:
                    failures.append("pg_restore is not installed; DB dump was not validated.")
                except subprocess.CalledProcessError as exc:
                    failures.append(
                        f"Unreadable PostgreSQL dump {path.name}: {exc.stderr.strip()}"
                    )

        if failures:
            raise CommandError("Backup verification failed — " + "; ".join(failures))

        self.stdout.write(
            self.style.SUCCESS(f"Backup verified successfully: {manifest_path}")
        )
