"""Phase 8 PostgreSQL restore verifier tests require no database or VPS access."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from scripts.phase8_postgres_restore_drill import (
    RestoreDrillError,
    clean_pg_environment,
    restore_safe_media,
    verify_manifest,
)


class RestoreDrillArchiveTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="leosoft-restore-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "database.postgresql.dump"
        self.database.write_bytes(b"test-dump-placeholder")
        self.media = self.root / "media.tar.gz"
        self._build_archive()
        self.manifest = self.root / "manifest.json"
        self._write_manifest()

    def _build_archive(self, *, unsafe: str = "", symbolic: bool = False):
        with tarfile.open(self.media, "w:gz") as tar:
            for directory in ("media", "private_media"):
                entry = tarfile.TarInfo(directory)
                entry.type = tarfile.DIRTYPE
                tar.addfile(entry)
            if symbolic:
                entry = tarfile.TarInfo("media/bad-link")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/passwd"
                tar.addfile(entry)
            else:
                content = b"sample private repair attachment"
                entry = tarfile.TarInfo(
                    unsafe or "private_media/repair/test.jpg"
                )
                entry.size = len(content)
                tar.addfile(entry, BytesIO(content))

    def _write_manifest(self, *, include_media: bool = True):
        paths = [self.database]
        if include_media:
            paths.append(self.media)
        records = [
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ]
        self.manifest.write_text(
            json.dumps({
                "database_engine": "django.db.backends.postgresql",
                "release": "test-release",
                "files": records,
            }), encoding="utf-8"
        )

    def test_valid_checksums_and_private_media_are_recoverable(self):
        database, archive, metadata = verify_manifest(self.manifest)
        self.assertEqual(database, self.database)
        self.assertEqual(archive, self.media)
        self.assertEqual(metadata["release"], "test-release")
        destination = self.root / "extracted"
        self.assertEqual(restore_safe_media(archive, destination), 1)
        self.assertEqual(
            (destination / "private_media/repair/test.jpg").read_bytes(),
            b"sample private repair attachment",
        )
        self.assertTrue((destination / "media").is_dir())

    def test_requires_media_for_full_recovery_certification(self):
        self._write_manifest(include_media=False)
        with self.assertRaisesMessage(RestoreDrillError, "Media archive missing"):
            verify_manifest(self.manifest)

    def test_rejects_corrupt_dump_even_with_valid_manifest_format(self):
        # Preserve original size so this specifically tests the checksum.
        # A changed length should be rejected even earlier by size validation.
        self.database.write_bytes(b"corrupt-dump" + b"x" * (len(b"test-dump-placeholder") - len(b"corrupt-dump")))
        with self.assertRaisesMessage(RestoreDrillError, "checksum mismatch"):
            verify_manifest(self.manifest)

    def test_rejects_dump_size_mismatch_before_checksum_verification(self):
        self.database.write_bytes(b"truncated")
        with self.assertRaisesMessage(RestoreDrillError, "size mismatch"):
            verify_manifest(self.manifest)

    def test_rejects_archive_path_traversal(self):
        self._build_archive(unsafe="../../not-allowed.txt")
        self._write_manifest()
        _, media, _ = verify_manifest(self.manifest)
        with self.assertRaisesMessage(RestoreDrillError, "unsafe"):
            restore_safe_media(media, self.root / "extracted")
        self.assertFalse((self.root.parent / "not-allowed.txt").exists())

    def test_rejects_archive_symlinks(self):
        self._build_archive(symbolic=True)
        self._write_manifest()
        _, media, _ = verify_manifest(self.manifest)
        with self.assertRaisesMessage(RestoreDrillError, "unsafe"):
            restore_safe_media(media, self.root / "extracted")
        self.assertFalse((self.root / "extracted/media/bad-link").exists())

    def test_rejects_duplicate_manifest_names(self):
        metadata = json.loads(self.manifest.read_text())
        metadata["files"].append(dict(metadata["files"][0]))
        self.manifest.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesMessage(RestoreDrillError, "duplicate"):
            verify_manifest(self.manifest)

    def test_rejects_symlinked_dump(self):
        other = self.root / "external.dump"
        other.write_bytes(self.database.read_bytes())
        self.database.unlink()
        self.database.symlink_to(other)
        with self.assertRaisesMessage(RestoreDrillError, "missing or unsafe"):
            verify_manifest(self.manifest)

    def test_pg_environment_cannot_target_configured_production_host(self):
        from unittest.mock import patch

        with patch.dict(
            "os.environ",
            {
                "PGHOST": "production.example.com",
                "PGPASSWORD": "production-secret",
                "PGSERVICE": "production",
                "PGPORT": "6543",
                "ALLTECH_DB_PASSWORD": "production-secret",
                "DATABASE_URL": "postgres://production.example.com/main",
            },
        ):
            clean = clean_pg_environment(self.root / "isolated", "test-user")
        self.assertEqual(clean["PGHOST"], str(self.root / "isolated"))
        self.assertEqual(clean["PGUSER"], "test-user")
        self.assertEqual(clean["PGPORT"], "5432")
        self.assertNotIn("PGPASSWORD", clean)
        self.assertNotIn("PGSERVICE", clean)
        self.assertNotIn("ALLTECH_DB_PASSWORD", clean)
        self.assertNotIn("DATABASE_URL", clean)
