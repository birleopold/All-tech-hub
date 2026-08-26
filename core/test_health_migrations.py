import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from core.health import ready


class MigrationReadinessTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/health/ready/")

    def test_ready_reports_current_migration_state(self):
        response = ready(self.request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["database"], "ok")
        self.assertEqual(payload["migrations"], "ok")
        self.assertEqual(payload["pending_migrations"], [])

    @patch("core.health.MigrationExecutor")
    def test_ready_is_degraded_when_migration_is_pending(self, executor_class):
        migration = SimpleNamespace(app_label="automation", name="0004_social")
        executor = executor_class.return_value
        executor.loader.graph.leaf_nodes.return_value = [("automation", "0004_social")]
        executor.migration_plan.return_value = [(migration, False)]

        response = ready(self.request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "ok")
        self.assertEqual(payload["migrations"], "pending")
        self.assertEqual(
            payload["pending_migrations"],
            ["automation.0004_social"],
        )
