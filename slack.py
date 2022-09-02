from base64 import b64encode
from typing import Any, Dict, List

import os
import requests


class Notifier:
    def __init__(self, *channels: str):
        self._channels = list(channels) or self._missing_config("Slack channels target")
        self._user = os.getenv("SLACK_USER") or self._missing_config("SLACK_USER environment variable")
        self._token = os.getenv("SLACK_TOKEN") or self._missing_config("SLACK_TOKEN environment variable")
        self._url = (
            os.getenv("SLACK_NOTIFICATION_URL")
            or "https://slack-notifications.tax.service.gov.uk/slack-notifications/notification"
        )

    def send_info(self, header: str, title: str, text: str) -> None:
        self.send_message(header, title, text, "#36a64f")

    def send_error(self, header: str, title: str, text: str) -> None:
        self.send_message(header, title, text, "#ff4d4d")

    def send_message(self, header: str, title: str, text: str, color: str) -> None:
        try:
            self._handle_response(self._send(header, title, text, color))
        except requests.RequestException as err:
            raise SendSlackMessageException(self._url, self._channels, str(err)) from None

    def _missing_config(self, config: str) -> Any:
        raise MissingConfigException(config)

    def _send(self, header: str, title: str, text: str, color: str) -> Dict[str, Any]:
        response = requests.post(
            url=self._url,
            headers=self._build_headers(),
            json=self._build_payload(header, title, text, color),
            timeout=10,
        )
        response.raise_for_status()
        return dict(response.json())

    def _build_headers(self) -> Dict[str, str]:
        credentials = b64encode(f"{self._user}:{self._token}".encode("utf-8")).decode("utf-8")
        return {"Content-Type": "application/json", "Authorization": f"Basic {credentials}"}

    def _build_payload(self, header: str, title: str, text: str, color: str) -> Dict[str, Any]:
        return {
            "channelLookup": {
                "by": "slack-channel",
                "slackChannels": self._channels,
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
        }

    def _handle_response(self, response: Dict[str, Any]) -> None:
        errors = response.get("errors")
        exclusions = response.get("exclusions")
        if errors or exclusions:
            raise SendSlackMessageException(self._url, self._channels, f"errors: {errors}\nexclusions: {exclusions}")


class MissingConfigException(Exception):
    def __init__(self, config: str):
        super().__init__(f"{config} is missing")


class SendSlackMessageException(Exception):
    def __init__(self, url: str, channels: List[str], error: str):
        super().__init__(f"failed to send Slack notification to '{url}' for channels {channels}: {error}")
