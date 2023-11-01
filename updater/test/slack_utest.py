from typing import List, Dict, Any
from unittest import TestCase
from unittest.mock import patch

import httpretty
import json
import os

from updater import slack


class TestMissingConfig(TestCase):
    def test_missing_slack_channels(self) -> None:
        with self.assertRaisesRegex(slack.MissingConfigException, "Slack channels target"):
            slack.Notifier(display="user", emoji=":robot_face:")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_internal_auth_token(self) -> None:
        with self.assertRaisesRegex(slack.MissingConfigException, "INTERNAL_AUTH_TOKEN environment variable"):
            slack.Notifier("channel", display="user", emoji=":robot_face:")


@httpretty.activate
@patch.dict(os.environ, {"INTERNAL_AUTH_TOKEN": "token"}, clear=True)
class TestSlackNotifier(TestCase):
    def test_send_message(self) -> None:
        self._register_slack_api_success()
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "the message body"
                }
            }
        ]
        slack.Notifier("slack-channel", display="user", emoji=":robot_face:").send_message("the text", blocks)
        self._assert_headers_correct()
        self._assert_payload_correct(["slack-channel"], "user", ":robot_face:", "the text", blocks)

    def test_request_failure(self) -> None:
        self._register_slack_api_failure(403)
        with self.assertRaisesRegex(slack.SendSlackMessageException, "403"):
            slack.Notifier("channel", display="user", emoji=":robot_face:").send_message("some text", [])

    def test_slack_failure(self) -> None:
        self._register_slack_api_failure(200)
        with self.assertRaisesRegex(slack.SendSlackMessageException, "unknown-channel"):
            slack.Notifier("unknown-channel", display="user", emoji=":robot_face:").send_message("some text", [])

    @staticmethod
    def _register_slack_api_success() -> None:
        httpretty.register_uri(
            httpretty.POST,
            "https://slack-notifications.tax.service.gov.uk/slack-notifications/v2/notification",
            body=json.dumps({"successfullySentTo": ["slack-channel"]}),
            status=200,
        )

    @staticmethod
    def _register_slack_api_failure(status: int) -> None:
        httpretty.register_uri(
            httpretty.POST,
            "https://slack-notifications.tax.service.gov.uk/slack-notifications/v2/notification",
            body=json.dumps({"errors": [{"code": "error", "message": "statusCode: 404, msg: 'channel_not_found'"}]}),
            status=status,
        )

    def _assert_headers_correct(self) -> None:
        headers = httpretty.last_request().headers.items()
        self.assertIn(("Content-Type", "application/json"), headers)
        self.assertIn(("Authorization", "token"), headers)

    def _assert_payload_correct(self, channels: List[str], display:str, emoji:str, text: str, blocks: List[Dict[str, Any]]) -> None:
        self.assertEqual(
            {
                "channelLookup": {
                    "by": "slack-channel",
                    "slackChannels": channels,
                },
                "displayName": display,
                "emoji": emoji,
                "text": text,
                "blocks": blocks
            },
            json.loads(httpretty.last_request().body),
        )
