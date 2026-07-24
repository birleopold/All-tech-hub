from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = "Create a checksummed LEOSOFT database backup with optional media archive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-media",
            action="store_true",
            help="Archive public and private media alongside the database backup.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=int(os.getenv("ALLTECH_BACKUP_RETENTION_DAYS", "30")),
            help="Remove completed local backups older than this many days. Use 0 to disable.",
        )
        parser.add_argument(
            "--offsite",
            action="store_true",
            help="Copy the completed backup directory to ALLTECH_BACKUP_RCLONE_DEST.",
        )

    def handle(self, *args, **options):
        root = Path(settings.BACKUP_ROOT).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = timezone.now().strftime("%Y%m%dT%H%M%S%fZ")
        release = self._release_label()
        backup_dir = root / f"leosoft-{timestamp}-{release}"
        backup_dir.mkdir(mode=0o700)

        manifest = {
            "created_at": timezone.now().isoformat(),
            "release": release,
            "environment": os.getenv("ALLTECH_ENV", "development"),
            "database_engine": settings.DATABASES["default"]["ENGINE"],
            "files": [],
        }

        try:
            database_path = self._backup_database(backup_dir)
            manifest["files"].append(self._file_record(database_path))
            if options["include_media"]:
                media_path = self._archive_media(backup_dir)
                if media_path is not None:
                    manifest["files"].append(self._file_record(media_path))

            manifest_path = backup_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            manifest_path.chmod(0o600)
            self._verify_manifest(backup_dir, manifest)
        except Exception:
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise

        self._remove_expired_backups(
            root,
            current=backup_dir,
            retention_days=max(0, options["retention_days"]),
        )
        if options["offsite"]:
            self._copy_offsite(backup_dir)

        self.stdout.write(self.style.SUCCESS(f"Backup completed: {backup_dir}"))
        for record in manifest["files"]:
            self.stdout.write(
                f"- {record['name']} ({record['size_bytes']} bytes) "
                f"sha256={record['sha256']}"
            )

    def _backup_database(self, backup_dir: Path) -> Path:
        database = settings.DATABASES["default"]
        engine = database["ENGINE"]
        if engine.endswith("sqlite3"):
            destination = backup_dir / "database.sqlite3"
            connection = connections["default"]
            connection.ensure_connection()
            source_connection = connection.connection
            if source_connection is None:
                raise CommandError("SQLite connection could not be opened.")
            with sqlite3.connect(destination) as destination_connection:
                source_connection.backup(destination_connection)
            destination.chmod(0o600)
            return destination

        if engine in {
            "django.db.backends.postgresql",
            "django.db.backends.postgresql_psycopg2",
        }:
            executable = shutil.which("pg_dump")
            if not executable:
                raise CommandError("pg_dump is required for PostgreSQL backups.")
            destination = backup_dir / "database.postgresql.dump"
            command = [
                executable,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(destination),
            ]
            if database.get("HOST"):
                command.extend(["--host", str(database["HOST"])])
            if database.get("PORT"):
                command.extend(["--port", str(database["PORT"])])
            if database.get("USER"):
                command.extend(["--username", str(database["USER"])])
            command.append(str(database["NAME"]))
            environment = os.environ.copy()
            if database.get("PASSWORD"):
                environment["PGPASSWORD"] = str(database["PASSWORD"])
            sslmode = (database.get("OPTIONS") or {}).get("sslmode")
            if sslmode:
                environment["PGSSLMODE"] = str(sslmode)
            subprocess.run(
                command,
                check=True,
                env=environment,
                stdout=subprocess.DEVNULL,
            )
            destination.chmod(0o600)
            return destination

        raise CommandError(f"Unsupported database backend for verified backup: {engine}")

    @staticmethod
    def _archive_media(backup_dir: Path) -> Path | None:
        sources = []
        for name, configured_path in (
            ("media", settings.MEDIA_ROOT),
            ("private_media", settings.PRIVATE_MEDIA_ROOT),
        ):
            path = Path(configured_path).expanduser().resolve()
            if path.exists() and path.is_dir():
                sources.append((name, path))
        if not sources:
            return None

        destination = backup_dir / "media.tar.gz"
        with tarfile.open(destination, "w:gz") as archive:
            for name, source in sources:
                archive.add(source, arcname=name, recursive=True)
        destination.chmod(0o600)
        return destination

    @staticmethod
    def _file_record(path: Path) -> dict:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }

    def _verify_manifest(self, backup_dir: Path, manifest: dict) -> None:
        for record in manifest["files"]:
            path = backup_dir / record["name"]
            if not path.exists() or path.stat().st_size != record["size_bytes"]:
                raise CommandError(f"Backup verification failed for {path.name}.")
            if self._file_record(path)["sha256"] != record["sha256"]:
                raise CommandError(f"Checksum verification failed for {path.name}.")

    @staticmethod
    def _remove_expired_backups(
        root: Path,
        *,
        current: Path,
        retention_days: int,
    ) -> None:
        if retention_days <= 0:
            return
        cutoff = timezone.now() - timedelta(days=retention_days)
        for candidate in root.glob("leosoft-*"):
            if candidate == current or not candidate.is_dir():
                continue
            modified = datetime.fromtimestamp(
                candidate.stat().st_mtime,
                tz=timezone.get_current_timezone(),
            )
            if modified < cutoff:
                shutil.rmtree(candidate)

    @staticmethod
    def _copy_offsite(backup_dir: Path) -> None:
        destination = os.getenv("ALLTECH_BACKUP_RCLONE_DEST", "").strip()
        if not destination:
            raise CommandError(
                "ALLTECH_BACKUP_RCLONE_DEST is required when --offsite is used."
            )
        executable = shutil.which("rclone")
        if not executable:
            raise CommandError("rclone is required for off-site backup copies.")
        target = f"{destination.rstrip('/')}/{backup_dir.name}"
        subprocess.run(
            [executable, "copy", str(backup_dir), target, "--checksum"],
            check=True,
        )

    @staticmethod
    def _release_label() -> str:
        label = os.getenv("ALLTECH_RELEASE_SHA", "").strip()
        if not label:
            marker = Path(settings.BASE_DIR) / ".release"
            try:
                label = marker.read_text(encoding="utf-8").strip()
            except OSError:
                label = ""
        safe = "".join(character for character in label if character.isalnum())
        return safe[:16] or "unknown"
