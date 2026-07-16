import json

from django.test import SimpleTestCase, override_settings

from automation.connectors import MetaConfig, _parse_graph_error


class MetaConnectorSafetyTests(SimpleTestCase):
    @override_settings(
        META_AUTO_PUBLISH_ENABLED=False,
        META_PAGE_ID="page-id",
        META_INSTAGRAM_ACCOUNT_ID="instagram-id",
        META_PAGE_ACCESS_TOKEN="secret-token",
    )
    def test_disabled_connector_supports_no_channels(self):
        config = MetaConfig.load()
        self.assertFalse(config.supports("facebook"))
        self.assertFalse(config.supports("instagram"))

    def test_media_processing_error_is_retryable(self):
        raw = json.dumps(
            {
                "error": {
                    "message": "Media ID is not available. The media is still processing.",
                    "code": 9007,
                    "error_subcode": 2207027,
                }
            }
        ).encode("utf-8")

        error = _parse_graph_error(raw, 400)

        self.assertTrue(error.retryable)
        self.assertEqual(error.code, "9007:2207027")

    def test_permission_error_is_permanent_and_does_not_echo_tokens(self):
        raw = json.dumps(
            {
                "error": {
                    "message": "Permissions error",
                    "code": 200,
                }
            }
        ).encode("utf-8")

        error = _parse_graph_error(raw, 403)

        self.assertFalse(error.retryable)
        self.assertNotIn("access_token", str(error))
