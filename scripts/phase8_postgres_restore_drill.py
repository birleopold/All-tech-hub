#!/usr/bin/env python3
"""Rehearse a LEOSOFT PostgreSQL + media backup in a disposable local cluster.

NEVER uses production database credentials, host, socket or PostgreSQL service.
Requires server binaries for a private, local-only PostgreSQL instance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone


class RestoreDrillError(RuntimeError):
    """A backup cannot be safely and completely rehearsed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(path: Path) -> tuple[Path, Path, dict]:
    """Verify the production backup's files before touching temporary storage."""
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise RestoreDrillError("Expected a backup manifest file.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RestoreDrillError("Backup manifest is unreadable.") from exc
    if manifest.get("database_engine") not in {
        "django.db.backends.postgresql",
        "django.db.backends.postgresql_psycopg2",
    }:
        raise RestoreDrillError("This drill requires a PostgreSQL backup manifest.")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise RestoreDrillError("Backup manifest contains no files.")
    by_name: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict):
            raise RestoreDrillError("Invalid backup file record.")
        name = record.get("name")
        if (
            not isinstance(name, str)
            or not name
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
            or name in by_name
        ):
            raise RestoreDrillError("Unsafe or duplicate backup file name.")
        candidate = path.parent / name
        if not candidate.is_file() or candidate.is_symlink():
            raise RestoreDrillError(f"Backup file missing or unsafe: {name}.")
        size = record.get("size_bytes")
        digest = record.get("sha256")
        if type(size) is not int or size < 0 or candidate.stat().st_size != size:
            raise RestoreDrillError(f"Backup size mismatch: {name}.")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise RestoreDrillError(f"Missing or invalid checksum for {name}.")
        if sha256(candidate) != digest.lower():
            raise RestoreDrillError(f"Backup checksum mismatch: {name}.")
        by_name[name] = candidate
    if "database.postgresql.dump" not in by_name:
        raise RestoreDrillError("PostgreSQL dump is missing from the manifest.")
    if "media.tar.gz" not in by_name:
        raise RestoreDrillError(
            "Media archive missing. Create a backup with --include-media "
            "before claiming complete recovery."
        )
    return by_name["database.postgresql.dump"], by_name["media.tar.gz"], manifest


def restore_safe_media(archive_path: Path, target: Path) -> int:
    """Extract plain files/directories only, never links or traversal members."""
    target.mkdir(mode=0o700)
    restored = 0
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                raw_name = member.name
                member_path = PurePosixPath(raw_name)
                if (
                    not raw_name
                    or "\\" in raw_name
                    or not member_path.parts
                    or member_path.is_absolute()
                    or ".." in member_path.parts
                    or member_path.parts[0] not in {"media", "private_media"}
                    or not (member.isdir() or member.isfile())
                ):
                    raise RestoreDrillError(
                        "Media archive has an unsafe file, link or directory entry."
                    )
                destination = target.joinpath(*member_path.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if destination.exists():
                    raise RestoreDrillError("Media archive has duplicate file entries.")
                payload = archive.extractfile(member)
                if payload is None:
                    raise RestoreDrillError("Media archive file could not be read.")
                with payload, destination.open("xb") as output:
                    shutil.copyfileobj(payload, output, 1024 * 1024)
                restored += 1
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise RestoreDrillError("Media archive is unreadable.") from exc
    return restored


def find_postgres_bin() -> Path:
    candidates: list[Path] = []
    pg_config = shutil.which("pg_config")
    if pg_config:
        try:
            directory = subprocess.check_output(
                [pg_config, "--bindir"], text=True
            ).strip()
            candidates.append(Path(directory))
        except subprocess.CalledProcessError:
            pass
    for location in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        candidates.append(location)
    if shutil.which("initdb"):
        candidates.append(Path(shutil.which("initdb")).parent)
    required = ("initdb", "pg_ctl", "createdb", "pg_restore", "psql")
    for candidate in candidates:
        if all((candidate / name).is_file() for name in required):
            return candidate
    raise RestoreDrillError(
        "PostgreSQL server tools are required (initdb, pg_ctl, "
        "createdb, pg_restore and psql)."
    )


def clean_pg_environment(socket_dir: Path, username: str) -> dict[str, str]:
    """Prevent inherited PGHOST/PGPASSWORD/PGSERVICE targeting production."""
    environment = {
        key: val for key, val in os.environ.items()
        if not key.startswith("PG") and not key.startswith("ALLTECH_DB_")
        and key not in {"DATABASE_URL", "DJANGO_SETTINGS_MODULE"}
    }
    environment.update(
        PGHOST=str(socket_dir),
        PGPORT="5432",
        PGUSER=username,
        PGDATABASE="postgres",
        PGAPPNAME="leosoft-restore-drill",
    )
    return environment


def run_drill(manifest_path: Path, *, work_root: Path | None = None) -> dict:
    if os.geteuid() == 0:
        raise RestoreDrillError("Do not run a PostgreSQL restore drill as root.")
    database, media, manifest = verify_manifest(manifest_path)
    tools = find_postgres_bin()
    username = pwd.getpwuid(os.geteuid()).pw_name

    with tempfile.TemporaryDirectory(
        prefix="leosoft-pg-restore-", dir=work_root
    ) as directory:
        root = Path(directory)
        root.chmod(0o700)
        data_dir = root / "pgdata"
        socket_dir = root / "socket"
        socket_dir.mkdir(mode=0o700)
        media_count = restore_safe_media(media, root / "restored-media")
        environment = clean_pg_environment(socket_dir, username)

        def pg(command: str, *args: str, capture: bool = False):
            return subprocess.run(
                [str(tools / command), *args],
                check=True,
                env=environment,
                text=True,
                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            )

        started = False
        try:
            pg(
                "initdb", "--no-instructions",
                "--auth-local=trust", "--auth-host=reject",
                "-D", str(data_dir),
            )
            pg(
                "pg_ctl", "-D", str(data_dir), "-w", "-l", str(root / "postgres.log"),
                "-o", f"-c listen_addresses='' -c unix_socket_directories='{socket_dir}'",
                "start",
            )
            started = True
            target_db = "leosoft_restore_rehearsal"
            pg("createdb", "--maintenance-db=postgres", target_db)
            pg(
                "pg_restore", "--exit-on-error", "--single-transaction",
                "--no-owner", "--no-privileges", "--dbname", target_db,
                str(database),
            )
            migrations = pg(
                "psql", "-X", "-qAt", "-d", target_db,
                "-c", "SELECT COUNT(*) FROM django_migrations",
                capture=True,
            ).stdout.strip()
            tables = pg(
                "psql", "-X", "-qAt", "-d", target_db,
                "-c", "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'",
                capture=True,
            ).stdout.strip()
            if not migrations.isdecimal() or int(migrations) == 0:
                raise RestoreDrillError("Restored database has no Django migrations.")
            if not tables.isdecimal() or int(tables) == 0:
                raise RestoreDrillError("Restored database has no public tables.")
            return {
                "status": "passed",
                "backup_release": str(manifest.get("release") or "unknown")[:40],
                "django_migrations": int(migrations),
                "public_tables": int(tables),
                "restored_media_files": media_count,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "production_database_accessed": False,
            }
        finally:
            if started:
                try:
                    pg("pg_ctl", "-D", str(data_dir), "-m", "fast", "-w", "stop")
                except subprocess.CalledProcessError:
                    pg("pg_ctl", "-D", str(data_dir), "-m", "immediate", "-w", "stop")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to checksummed backup manifest.json")
    parser.add_argument(
        "--work-root", type=Path, default=None,
        help="An existing location with enough free disk; only private temporary files are created",
    )
    args = parser.parse_args()
    try:
        report = run_drill(args.manifest, work_root=args.work_root)
    except (RestoreDrillError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"PostgreSQL restore drill FAILED: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
