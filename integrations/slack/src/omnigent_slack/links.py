from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from omnigent_slack.models import ThreadKey

if TYPE_CHECKING:
    from omnigent_slack.streaming import SlackClientProtocol


def native_link(server_url: str, session_id: str, elicitation_id: str | None = None) -> str | None:
    """Routes declared by the native web App: /c/:id and /approve/:session/:elicitation."""
    try:
        origin = urlsplit(server_url)
        if (
            origin.scheme not in ("http", "https")
            or not origin.hostname
            or origin.username is not None
            or origin.password is not None
            or origin.query
            or origin.fragment
            or any(char.isspace() or char in "<>|\\" for char in server_url)
            or not session_id
        ):
            return None
        _ = origin.port
    except ValueError:
        return None
    session = quote(session_id, safe="")
    route = (
        f"/c/{session}"
        if elicitation_id is None
        else f"/approve/{session}/{quote(elicitation_id, safe='')}"
    )
    return server_url.rstrip("/") + route


async def native_link_unavailable(client: SlackClientProtocol, key: ThreadKey) -> str:
    try:
        response = await client.chat_getPermalink(channel=key.channel_id, message_ts=key.thread_ts)
        permalink = response.get("permalink")
        if isinstance(permalink, str) and permalink.startswith("https://"):
            return f"Native link unavailable; <{permalink}|continue in this Slack thread>."
    except Exception:
        pass
    return "Native link unavailable; Slack permalink unavailable. Continue in this Slack thread."
