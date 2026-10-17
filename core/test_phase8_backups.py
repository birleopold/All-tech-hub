"""Phase 8 verifier tests operate only on ephemeral files."""
import hashlib
import json
import sqlite3
import tarfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class BackupIntegrityTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="phase8-verifier-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "manifest.json"

    def _manifest(self, paths):
        records = [{
            "name": file.name,
            "size_bytes": file.stat().st_size,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        } for file in paths]
        self.manifest.write_text(json.dumps({"files": records}), encoding="utf-8")

    def _sqlite(self):
        file = self.root / "database.sqlite3"
        with sqlite3.connect(file) as connection:
            connection.execute("CREATE TABLE drill (id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO drill VALUES (1)")
        return file

    def test_verifies_valid_sqlite(self):
        self._manifest([self._sqlite()])
        call_command("verify_alltech_backup", str(self.manifest))

    def test_rejects_corrupt_sqlite_even_when_checksum_matches(self):
        file = self.root / "database.sqlite3"
        file.write_bytes(b"not a sqlite database")
        self._manifest([file])
        with self.assertRaisesMessage(CommandError, "Unreadable SQLite"):
            call_command("verify_alltech_backup", str(self.manifest))

    def test_verifies_tar_readability_not_only_checksum(self):
        archive_path = self.root / "media.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            payload = b"test media"
            member = tarfile.TarInfo("media/test.txt")
            member.size = len(payload)
            archive.addfile(member, BytesIO(payload))
        database = self._sqlite()
        self._manifest([database, archive_path])
        call_command("verify_alltech_backup", str(self.manifest))
        archive_path.write_bytes(b"not gzip content")
        self._manifest([database, archive_path])
        with self.assertRaisesMessage(CommandError, "Unreadable media archive"):
            call_command("verify_alltech_backup", str(self.manifest))

    def test_rejects_manifest_path_traversal(self):
        self.manifest.write_text(json.dumps({"files": [{
            "name": "../outside.sqlite3", "size_bytes": 10, "sha256": "0" * 64,
        }]}), encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "Unsafe or invalid"):
            call_command("verify_alltech_backup", str(self.manifest))

    def test_rejects_empty_manifest(self):
        self.manifest.write_text('{"files": []}', encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "no file entries"):
            call_command("verify_alltech_backup", str(self.manifest))
