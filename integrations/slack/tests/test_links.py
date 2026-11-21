import logging
from unittest.mock import AsyncMock

import pytest
from omnigent_slack.links import native_link, native_link_unavailable
from omnigent_slack.models import ThreadKey
from omnigent_slack.notifications import SlackNotifier


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "not-a-url",
        "javascript:alert(1)",
        "//example.test",
        "https://user:pass@example.test",
        "https://example.test?redirect=x",
        "https://example.test/#x",
        "https://example.test:bad",
        "https://example.test|bad",
    ],
)
def test_native_link_rejects_unusable_origin(origin: str) -> None:
    assert native_link(origin, "conv_1") is None


def test_native_routes_match_web_app_and_escape_identifiers() -> None:
    assert (
        native_link("https://example.test/prefix/", "conv_1")
        == "https://example.test/prefix/c/conv_1"
    )
    assert (
        native_link("https://example.test", "conv/1", "elicit?#1")
        == "https://example.test/approve/conv%2F1/elicit%3F%231"
    )


async def test_native_link_unavailable_uses_slack_permalink() -> None:
    client = AsyncMock()
    client.chat_getPermalink.return_value = {"permalink": "https://slack.test/archives/C1/p1001"}
    key = ThreadKey("T1", "C1", "100.1")
    notifier = SlackNotifier(server_url="", logger=logging.getLogger("test.links"))
    await notifier.post_session_info(
        client, key, harness=None, agent_name=None, workspace=None, session_id="conv_1"
    )
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "Native link unavailable" in text
    assert "https://slack.test/archives/C1/p1001" in text
    assert "/c/conv_1" not in text


async def test_native_link_unavailable_reports_permalink_failure() -> None:
    client = AsyncMock()
    client.chat_getPermalink.side_effect = RuntimeError("offline")
    assert "Slack permalink unavailable" in await native_link_unavailable(
        client, ThreadKey("T1", "C1", "100.1")
    )
