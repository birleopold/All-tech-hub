from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone


@dataclass(frozen=True, slots=True)
class BackupStatus:
    exists: bool
    healthy: bool
    path: Path | None
    created_at: datetime | None
    age_hours: float | None
    detail: str


def latest_backup_status(root: Path | None = None) -> BackupStatus:
    try:
        backup_root = Path(root or settings.BACKUP_ROOT).expanduser().resolve()
        if not backup_root.exists():
            return BackupStatus(
                False,
                False,
                None,
                None,
                None,
                "Backup directory is missing",
            )
        candidates = [
            path for path in backup_root.glob("leosoft-*") if path.is_dir()
        ]
        # Older scheduled releases used flat alltech-backup manifests. Keep them
        # visible while servers transition to the unified verified backup job.
        candidates.extend(
            path
            for path in backup_root.glob("alltech-backup-*.json")
            if path.is_file()
        )
    except OSError:
        return BackupStatus(
            False,
            False,
            None,
            None,
            None,
            "Backup storage is inaccessible",
        )

    if not candidates:
        return BackupStatus(False, False, None, None, None, "No completed backup found")

    try:
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        created_at = datetime.fromtimestamp(
            latest.stat().st_mtime,
            tz=timezone.get_current_timezone(),
        )
    except OSError:
        return BackupStatus(
            True,
            False,
            None,
            None,
            None,
            "Backup metadata is inaccessible",
        )

    age_hours = max(0.0, (timezone.now() - created_at).total_seconds() / 3600)
    manifest_path = latest if latest.is_file() else latest / "manifest.json"
    backup_files_root = latest.parent if latest.is_file() else latest
    try:
        manifest_exists = manifest_path.exists()
    except OSError:
        manifest_exists = False
    if not manifest_exists:
        return BackupStatus(
            True,
            False,
            latest,
            created_at,
            age_hours,
            "Manifest is missing or inaccessible",
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BackupStatus(
            True,
            False,
            latest,
            created_at,
            age_hours,
            "Manifest is unreadable",
        )

    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        return BackupStatus(
            True,
            False,
            latest,
            created_at,
            age_hours,
            "Manifest contains no backup files",
        )
    for record in records:
        if not isinstance(record, dict) or not record.get("name"):
            return BackupStatus(
                True,
                False,
                latest,
                created_at,
                age_hours,
                "Manifest contains an invalid file record",
            )
        file_path = backup_files_root / str(record["name"])
        expected_size = record.get("size_bytes")
        try:
            actual_size = file_path.stat().st_size
        except OSError:
            actual_size = None
        if not isinstance(expected_size, int) or actual_size != expected_size:
            return BackupStatus(
                True,
                False,
                latest,
                created_at,
                age_hours,
                f"Backup file is missing or incomplete: {record['name']}",
            )

    return BackupStatus(
        True,
        True,
        latest,
        created_at,
        age_hours,
        "Latest backup manifest and file sizes are valid",
    )
