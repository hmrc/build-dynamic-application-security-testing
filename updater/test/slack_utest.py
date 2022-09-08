from typing import List
from unittest import TestCase
from unittest.mock import patch

import httpretty
import json
import os

from updater import slack


class TestMissingConfig(TestCase):
    def test_missing_slack_channels(self) -> None:
        with self.assertRaisesRegex(slack.MissingConfigException, "Slack channels target"):
            slack.Notifier()

    @patch.dict(os.environ, {"SLACK_TOKEN": "token"}, clear=True)
    def test_missing_slack_user(self) -> None:
        with self.assertRaisesRegex(slack.MissingConfigException, "SLACK_USER environment variable"):
            slack.Notifier("channel")

    @patch.dict(os.environ, {"SLACK_USER": "user"}, clear=True)
    def test_missing_slack_token(self) -> None:
        with self.assertRaisesRegex(slack.MissingConfigException, "SLACK_TOKEN environment variable"):
            slack.Notifier("channel")


@httpretty.activate
@patch.dict(os.environ, {"SLACK_USER": "user", "SLACK_TOKEN": "token"}, clear=True)
class TestSlackNotifier(TestCase):
    def test_send_info_message(self) -> None:
        self._register_slack_api_success()
        slack.Notifier("slack-channel").send_info("the header", "the title", "the text")
        self._assert_headers_correct()
        self._assert_payload_correct(["slack-channel"], "the header", "the title", "the text", "#36a64f")

    def test_send_error_message(self) -> None:
        self._register_slack_api_success()
        slack.Notifier("a", "b", "c").send_error("some header", "some title", "some text")
        self._assert_headers_correct()
        self._assert_payload_correct(["a", "b", "c"], "some header", "some title", "some text", "#ff4d4d")

    def test_request_failure(self) -> None:
        self._register_slack_api_failure(403)
        with self.assertRaisesRegex(slack.SendSlackMessageException, "403"):
            slack.Notifier("channel").send_info("some header", "some title", "some text")

    def test_slack_failure(self) -> None:
        self._register_slack_api_failure(200)
        with self.assertRaisesRegex(slack.SendSlackMessageException, "unknown-channel"):
            slack.Notifier("unknown-channel").send_info("some header", "some title", "some text")

    @staticmethod
    def _register_slack_api_success() -> None:
        httpretty.register_uri(
            httpretty.POST,
            "https://slack-notifications.tax.service.gov.uk/slack-notifications/notification",
            body=json.dumps({"successfullySentTo": ["slack-channel"]}),
            status=200,
        )

    @staticmethod
    def _register_slack_api_failure(status: int) -> None:
        httpretty.register_uri(
            httpretty.POST,
            "https://slack-notifications.tax.service.gov.uk/slack-notifications/notification",
            body=json.dumps({"errors": [{"code": "error", "message": "statusCode: 404, msg: 'channel_not_found'"}]}),
            status=status,
        )

    def _assert_headers_correct(self) -> None:
        headers = httpretty.last_request().headers.items()
        self.assertIn(("Content-Type", "application/json"), headers)
        self.assertIn(("Authorization", "Basic dXNlcjp0b2tlbg=="), headers)  # base64 of "user:token"

    def _assert_payload_correct(self, channels: List[str], header: str, title: str, text: str, color: str) -> None:
        self.assertEqual(
            {
                "channelLookup": {
                    "by": "slack-channel",
                    "slackChannels": channels,
                },
                "messageDetails": {
                    "text": header,
                    "attachments": [
                        {
                            "color": color,
                            "title": title,
                            "text": text,
                        }
                    ],
                },
            },
            json.loads(httpretty.last_request().body),
        )
