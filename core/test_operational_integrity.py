from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from core.backups import latest_backup_status


class BackupCompatibilityTests(SimpleTestCase):
    def _create_current_backup(self, root: Path) -> Path:
        backup_dir = root / "leosoft-20260824T120000000000Z-test"
        backup_dir.mkdir(parents=True)
        database = backup_dir / "database.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE health_check (id INTEGER PRIMARY KEY)")
        payload = database.read_bytes()
        manifest = {
            "created_at": "2026-08-24T12:00:00+00:00",
            "files": [
                {
                    "name": database.name,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ],
        }
        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_current_backup_layout_is_discovered_and_healthy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._create_current_backup(root)
            with override_settings(BACKUP_ROOT=root):
                status = latest_backup_status()
            self.assertTrue(status.exists)
            self.assertTrue(status.healthy)
            self.assertEqual(status.path, manifest.parent.resolve())

    def test_verifier_defaults_to_current_backup_layout(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._create_current_backup(root)
            with override_settings(BACKUP_ROOT=root):
                call_command("verify_alltech_backup", verbosity=0)


class ProductionAutomationUnitTests(SimpleTestCase):
    def test_tracked_service_runs_controlled_orchestrator(self):
        service = (
            Path(__file__).resolve().parents[1]
            / "deployment"
            / "leosoft-marketing-posts.service"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "manage.py run_growth_automation --source timer --limit 100",
            service,
        )
        self.assertNotIn("manage.py run_automation_jobs", service)

    def test_operational_monitor_timer_runs_the_existing_monitor_command(self):
        root = Path(__file__).resolve().parents[1]
        service = (
            root / "deployment" / "leosoft-operations-monitor.service"
        ).read_text(encoding="utf-8")
        timer = (
            root / "deployment" / "leosoft-operations-monitor.timer"
        ).read_text(encoding="utf-8")
        self.assertIn("manage.py monitor_operations", service)
        self.assertIn("EnvironmentFile=/home/admin/All-tech-hub/.env", service)
        self.assertIn("OnUnitActiveSec=15min", timer)

    def test_production_management_helper_loads_the_same_environment(self):
        helper = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "manage_production.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('source "$ENV_FILE"', helper)
        self.assertIn('exec "${APP_DIR}/.venv/bin/python"', helper)


class ReliabilityRoleTests(TestCase):
    def test_finance_and_manager_receive_reliability_permissions(self):
        call_command("bootstrap_roles", verbosity=0)
        finance = Group.objects.get(name="Finance")
        manager = Group.objects.get(name="Manager")
        self.assertTrue(
            finance.permissions.filter(
                content_type__app_label="reliability",
                content_type__model="paymentattempt",
            ).exists()
        )
        self.assertTrue(
            manager.permissions.filter(
                content_type__app_label="reliability",
            ).exists()
        )
