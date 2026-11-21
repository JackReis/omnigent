"""
Opt-in reporter that POSTs per-turn LLM cost events to Paperclip.

Paperclip ingests cost events via ``POST /companies/:companyId/cost-events``
so an Omnigent agent's spend can be tracked alongside the rest of a
company's AI costs. This module is OFF by default: it activates only when
``OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED`` is truthy AND the base URL,
company id, and agent id are all configured. Delivery is fire-and-forget on
a daemon thread — an unreachable Paperclip is logged and swallowed, never
raised into the relay loop, and the ``session_usage`` ledger / cost-budget
policy are untouched.

Environment variables:

- ``OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED`` — ``1``/``true``/``yes``/``on``
  to enable; anything else (or unset) disables the reporter.
- ``OMNIGENT_PAPERCLIP_BASE_URL`` — Paperclip API origin, e.g.
  ``https://paperclip.example.com``.
- ``OMNIGENT_PAPERCLIP_COMPANY_ID`` — the ``:companyId`` path segment.
- ``OMNIGENT_PAPERCLIP_AGENT_ID`` — the ``agentId`` attributed on each event,
  e.g. ``"polly"``.
- ``OMNIGENT_PAPERCLIP_API_TOKEN`` — optional bearer token for the
  ``Authorization`` header.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial

import httpx

from omnigent.onboarding.providers import _inferred_catalog_provider

_logger = logging.getLogger(__name__)

ENABLED_ENV_VAR = "OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED"
BASE_URL_ENV_VAR = "OMNIGENT_PAPERCLIP_BASE_URL"
COMPANY_ID_ENV_VAR = "OMNIGENT_PAPERCLIP_COMPANY_ID"
AGENT_ID_ENV_VAR = "OMNIGENT_PAPERCLIP_AGENT_ID"
API_TOKEN_ENV_VAR = "OMNIGENT_PAPERCLIP_API_TOKEN"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_REQUEST_TIMEOUT_SECONDS = 5.0

# Warn once per process when the reporter is enabled but missing required
# config, instead of logging on every priced turn.
_warned_incomplete = False
_warned_lock = threading.Lock()


@dataclass(frozen=True)
class PaperclipConfig:
    """
    Resolved Paperclip reporting configuration.

    :param base_url: API origin without a trailing slash, e.g.
        ``"https://paperclip.example.com"``.
    :param company_id: The company whose cost-events endpoint is posted to.
    :param agent_id: The ``agentId`` attributed on every event.
    :param api_token: Optional bearer token; ``None`` sends no
        ``Authorization`` header.
    """

    base_url: str
    company_id: str
    agent_id: str
    api_token: str | None

    @property
    def cost_events_url(self) -> str:
        """The fully-resolved cost-events ingestion endpoint."""
        return f"{self.base_url}/companies/{self.company_id}/cost-events"


def load_paperclip_config() -> PaperclipConfig | None:
    """
    Read reporter configuration from the environment.

    Read per call (not cached) so a test or a long-lived process can toggle
    the flag without a restart; the cost is a few ``os.environ`` reads per
    priced turn.

    :returns: The resolved config, or ``None`` when reporting is disabled
        or required fields (base URL, company id, agent id) are missing.
    """
    if os.environ.get(ENABLED_ENV_VAR, "").strip().lower() not in _TRUTHY:
        return None
    base_url = os.environ.get(BASE_URL_ENV_VAR, "").strip().rstrip("/")
    company_id = os.environ.get(COMPANY_ID_ENV_VAR, "").strip()
    agent_id = os.environ.get(AGENT_ID_ENV_VAR, "").strip()
    if not (base_url and company_id and agent_id):
        global _warned_incomplete
        with _warned_lock:
            if not _warned_incomplete:
                _warned_incomplete = True
                _logger.warning(
                    "Paperclip cost reporting is enabled but missing one of "
                    "%s / %s / %s; no cost events will be sent",
                    BASE_URL_ENV_VAR,
                    COMPANY_ID_ENV_VAR,
                    AGENT_ID_ENV_VAR,
                )
        return None
    token = os.environ.get(API_TOKEN_ENV_VAR, "").strip() or None
    return PaperclipConfig(
        base_url=base_url, company_id=company_id, agent_id=agent_id, api_token=token
    )


def derive_provider(model: str) -> str:
    """
    Derive the billing provider name from an LLM model identifier.

    Provider-qualified ids use their namespace (``anthropic/claude-...`` →
    ``"anthropic"``); ``databricks-*`` ids are Databricks-served; bare ids
    fall back to the stable vendor-family prefixes the model catalog uses
    for routing (``claude-*`` → ``"anthropic"``, ``gpt-*`` → ``"openai"``,
    ...). Pure string matching — no catalog fetch — so it is safe on the
    relay hot path.

    :param model: Model id, e.g. ``"anthropic/claude-sonnet-4-6"``,
        ``"databricks-gpt-5-5"``, or ``"claude-opus-4-8"``.
    :returns: The provider name, or ``"unknown"`` when underivable.
    """
    normalized = model.split(":", 1)[0].strip()
    if "/" in normalized:
        namespace = normalized.split("/", 1)[0].strip().lower()
        return namespace or "unknown"
    if normalized.lower().startswith("databricks-"):
        return "databricks"
    return _inferred_catalog_provider(normalized) or "unknown"


def usd_to_cents(cost_usd: float) -> int:
    """
    Convert a USD amount to integer cents (Paperclip's ``costCents``).

    :param cost_usd: Cost in USD, e.g. ``0.05``.
    :returns: The amount rounded to the nearest whole cent, e.g. ``5``.
    """
    return round(cost_usd * 100)


def build_cost_event(
    *,
    agent_id: str,
    model: str,
    cost_usd: float,
    occurred_at: datetime,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> dict[str, object]:
    """
    Build one Paperclip cost-event payload.

    :param agent_id: The configured ``agentId``, e.g. ``"polly"``.
    :param model: The LLM model id the turn ran on.
    :param cost_usd: The turn's priced cost in USD.
    :param occurred_at: Aware timestamp of the usage write; normalized to
        UTC in the payload.
    :param input_tokens: Non-cached input tokens for the turn.
    :param output_tokens: Output tokens for the turn.
    :param cached_input_tokens: Cache-read input tokens for the turn.
    :returns: The JSON-serializable event body.
    """
    return {
        "agentId": agent_id,
        "provider": derive_provider(model),
        "model": model,
        "costCents": usd_to_cents(cost_usd),
        "occurredAt": occurred_at.astimezone(timezone.utc).isoformat(),
        "inputTokens": int(input_tokens),
        "outputTokens": int(output_tokens),
        "cachedInputTokens": int(cached_input_tokens),
    }


def _send(config: PaperclipConfig, payload: dict[str, object]) -> None:
    """
    POST one cost event to Paperclip, swallowing every failure.

    Runs on a background thread; any exception (connection refused, DNS,
    timeout, non-2xx) is logged at warning and dropped so an unreachable
    Paperclip can never affect the harness.
    """
    try:
        headers = {}
        if config.api_token:
            headers["Authorization"] = f"Bearer {config.api_token}"
        response = httpx.post(
            config.cost_events_url,
            json=payload,
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — reporting must never propagate
        _logger.warning("Paperclip cost event delivery failed: %s", exc)


def _submit(task: Callable[[], None]) -> None:
    """Run *task* on a daemon thread so delivery never blocks a turn."""
    threading.Thread(target=task, name="paperclip-cost-event", daemon=True).start()


def report_cost_event(
    *,
    model: str,
    cost_usd: float,
    occurred_at: datetime,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
) -> None:
    """
    Report one priced turn's cost to Paperclip, fire-and-forget.

    No-op when reporting is disabled or unconfigured. Called synchronously
    from the usage write sites; the HTTP POST itself happens on a daemon
    thread. Never raises — the callers sit inside the relay loop.

    :param model: The LLM model id the turn ran on.
    :param cost_usd: The turn's priced cost delta in USD.
    :param occurred_at: Aware timestamp captured at the usage write site.
    :param input_tokens: Non-cached input tokens for the turn.
    :param output_tokens: Output tokens for the turn.
    :param cached_input_tokens: Cache-read input tokens for the turn.
    :returns: None.
    """
    try:
        config = load_paperclip_config()
        if config is None:
            return
        payload = build_cost_event(
            agent_id=config.agent_id,
            model=model,
            cost_usd=cost_usd,
            occurred_at=occurred_at,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        _submit(partial(_send, config, payload))
    except Exception:  # noqa: BLE001 — reporting must never propagate
        _logger.warning("Paperclip cost event reporting failed", exc_info=True)
