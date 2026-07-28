from pathlib import Path

from django.test import SimpleTestCase


class DeploymentAutomationGateTests(SimpleTestCase):
    def setUp(self):
        self.script = (
            Path(__file__).resolve().parents[1] / "scripts" / "deploy_production.sh"
        ).read_text(encoding="utf-8")

    def test_release_requires_installed_enabled_and_active_timer(self):
        self.assertIn("ALLTECH_REQUIRE_AUTOMATION_TIMER", self.script)
        self.assertIn('systemctl cat "$AUTOMATION_TIMER_NAME"', self.script)
        self.assertIn('systemctl is-enabled --quiet "$AUTOMATION_TIMER_NAME"', self.script)
        self.assertIn('systemctl is-active --quiet "$AUTOMATION_TIMER_NAME"', self.script)
        self.assertIn('systemctl list-timers "$AUTOMATION_TIMER_NAME"', self.script)

    def test_release_controls_are_resolved_after_loading_env(self):
        source_position = self.script.index('source "$ENV_FILE"')
        resolved_position = self.script.index(
            'REQUIRE_AUTOMATION_TIMER="${ALLTECH_REQUIRE_AUTOMATION_TIMER:-1}"',
            source_position,
        )
        backup_position = self.script.index(
            'DEPLOY_BACKUP_ENABLED="${ALLTECH_DEPLOY_BACKUP_ENABLED:-1}"',
            source_position,
        )
        self.assertGreater(resolved_position, source_position)
        self.assertGreater(backup_position, source_position)

    def test_failure_output_includes_automation_diagnostics(self):
        self.assertIn('systemctl status "$AUTOMATION_TIMER_NAME"', self.script)
        self.assertIn('journalctl -u "$AUTOMATION_SERVICE_NAME"', self.script)
        self.assertIn("Install the tracked durable automation units", self.script)
