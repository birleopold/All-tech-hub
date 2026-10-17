"""Verify backup checksums and archive readability without restoring production."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

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
        records = manifest.get("files")
        if not isinstance(records, list) or not records:
            raise CommandError("Backup manifest contains no file entries.")
        for item in records:
            if not isinstance(item, dict):
                failures.append("Invalid backup manifest file entry.")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name or Path(name).name != name:
                failures.append("Unsafe or invalid file name in backup manifest.")
                continue
            path = manifest_path.parent / name
            if not path.is_file():
                failures.append(f"Missing: {path.name}")
                continue
            try:
                size = int(item.get("size_bytes", -1))
            except (ValueError, TypeError):
                size = -1
            if path.stat().st_size != size:
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
            elif path.suffix == ".sqlite3":
                try:
                    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as database:
                        result = database.execute("PRAGMA integrity_check").fetchone()
                    if result != ("ok",):
                        failures.append(f"SQLite integrity check failed: {path.name}")
                except (sqlite3.DatabaseError, OSError) as exc:
                    failures.append(f"Unreadable SQLite backup {path.name}: {exc}")
            elif path.name.endswith(".tar.gz"):
                try:
                    with tarfile.open(path, "r:gz") as archive:
                        for member in archive:
                            member_path = PurePosixPath(member.name)
                            if (
                                member_path.is_absolute()
                                or ".." in member_path.parts
                                or member.issym()
                                or member.islnk()
                            ):
                                failures.append(f"Unsafe media archive member: {member.name}")
                                break
                except (OSError, tarfile.TarError, EOFError) as exc:
                    failures.append(f"Unreadable media archive {path.name}: {exc}")
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
