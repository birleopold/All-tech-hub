#!/usr/bin/env python3
"""Conservative three-generation LEOSOFT local backup rotation.

Retain one newest daily, one older weekly (at least 7 days behind daily),
and one older monthly (at least 28 days behind daily). Do not prune until
three DISTINCT checksum-valid backups exist. Dry-run unless --apply.
"""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

NAME = re.compile(r"^leosoft-(\d{8}T\d{12}Z)-[0-9a-f]{7,40}$")


def verify(path: Path):
    try:
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            return None
        data = json.loads(manifest_path.read_text(encoding="utf8"))
        records = data["files"]
        if not isinstance(records, list) or not records:
            return None
        names = set()
        for rec in records:
            name, size, expected = rec["name"], rec["size_bytes"], rec["sha256"]
            if (not isinstance(name, str) or name in names
                    or Path(name).name != name or name.startswith(".")):
                return None
            names.add(name)
            file = path / name
            if file.is_symlink() or not file.is_file() or file.stat().st_size != size:
                return None
            digest = hashlib.sha256()
            with file.open("rb") as stream:
                for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(part)
            if digest.hexdigest() != expected:
                return None
        if not any(name.startswith("database.") for name in names):
            return None
        if "media.tar.gz" not in names:
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Delete extras after checks")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        parser.error("Backup root must be a directory, not a symlink")
    candidates = []
    unsafe = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink() or not NAME.fullmatch(path.name):
            continue
        stamp = datetime.strptime(NAME.fullmatch(path.name).group(1), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
        candidates.append((stamp, path))
    candidates.sort(reverse=True)
    if len(candidates) < 3:
        print("REFUSE: fewer than three candidate backups. No deletion.")
        return 2
    verified = []
    for stamp, path in candidates:
        if verify(path) is None:
            unsafe.append(path)
        else:
            verified.append((stamp, path))
    if len(verified) < 3:
        print("REFUSE: fewer than three checksum-verified backups. No deletion.")
        return 2
    daily_time, daily = verified[0]
    weekly = next(((dt, p) for dt, p in verified[1:] if dt <= daily_time - timedelta(days=7)), None)
    monthly = next(((dt, p) for dt, p in verified[1:] if dt <= daily_time - timedelta(days=28) and (weekly is None or p != weekly[1])), None)
    if weekly is None or monthly is None:
        print("REFUSE: need distinct verified daily, >=7-day weekly and >=28-day monthly points. No deletion.")
        return 2
    keep = {daily, weekly[1], monthly[1]}
    print("KEEP (3 verified recovery points):")
    for path in sorted(keep):
        print(" ", path.name)
    if unsafe:
        print(f"UNVERIFIED: {len(unsafe)} backups protected from automatic deletion")
    removable = [p for _, p in candidates if p not in keep and p not in unsafe]
    print(f"ELIGIBLE verified extras: {len(removable)}")
    if not args.apply:
        print("DRY RUN: no files deleted; rerun with --apply after review")
        return 0
    # Root and manifest checks repeated immediately before each deletion.
    for path in removable:
        if path.parent != root or path.is_symlink() or verify(path) is None:
            raise RuntimeError(f"Backup changed; stopping before removing {path}")
        shutil.rmtree(path)
        print("REMOVED", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
