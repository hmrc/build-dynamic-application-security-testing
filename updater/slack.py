from base64 import b64encode
from typing import Any, Dict, List

import os
import requests


class Notifier:
    def __init__(self, *channels: str, display: str, emoji: str):
        self._channels = list(channels) or self._missing_config("Slack channels target")
        self._display = display
        self._emoji = emoji
        self._token = os.getenv("INTERNAL_AUTH_TOKEN") or self._missing_config("INTERNAL_AUTH_TOKEN environment variable")
        self._url = (
            os.getenv("SLACK_NOTIFICATION_URL")
            or "https://slack-notifications.tax.service.gov.uk/slack-notifications/v2/notification"
        )

    def send_message(self, text: str, blocks: List[Dict[str, Any]]) -> None:
        try:
            self._handle_response(self._send(text, blocks))
        except requests.RequestException as err:
            raise SendSlackMessageException(self._url, self._channels, str(err)) from None

    def _missing_config(self, config: str) -> Any:
        raise MissingConfigException(config)

    def _send(self, text: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        response = requests.post(
            url=self._url,
            headers=self._build_headers(),
            json=self._build_payload(text, blocks),
            timeout=10,
        )
        response.raise_for_status()
        return dict(response.json())

    def _build_headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Authorization": self._token}

    def _build_payload(self, text: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "channelLookup": {
                "by": "slack-channel",
                "slackChannels": self._channels,
            },
            "displayName": self._display,
            "emoji": self._emoji,
            "text": text,
            "blocks": blocks
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
