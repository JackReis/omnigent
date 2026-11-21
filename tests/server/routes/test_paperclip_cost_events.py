"""Opt-in Paperclip cost-event reporting.

The reporter POSTs one cost event per priced turn to Paperclip's
``POST /companies/:companyId/cost-events`` ingestion API. It is OFF by
default, gated behind ``OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED``, and
must never raise into the relay loop — a dead Paperclip endpoint is
logged and swallowed. The ``session_usage`` ledger and cost-budget
semantics are unchanged by the hook.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from omnigent.server import paperclip_cost_events as pce
from omnigent.server.routes._sessions.orchestration import (
    _accumulate_session_usage,
    _persist_native_cumulative_usage,
)
from omnigent.stores.conversation_store.sqlalchemy_store import (
    SqlAlchemyConversationStore,
)

# Agent ids are stored as 16-byte uuids, so tests use a valid 32-char hex id.
_AGENT_ID = "0123456789abcdef0123456789abcdef"

_ALL_ENV_VARS = (
    "OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED",
    "OMNIGENT_PAPERCLIP_BASE_URL",
    "OMNIGENT_PAPERCLIP_COMPANY_ID",
    "OMNIGENT_PAPERCLIP_AGENT_ID",
    "OMNIGENT_PAPERCLIP_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _clean_paperclip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from the default (disabled, unconfigured) state."""
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED", "1")
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_BASE_URL", "http://paperclip.test")
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_COMPANY_ID", "co_123")
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_AGENT_ID", "polly")
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_API_TOKEN", "sekret")


def _capture_sends(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Run submits inline and record each payload instead of POSTing."""
    sent: list[dict[str, object]] = []
    monkeypatch.setattr(pce, "_submit", lambda task: task())
    monkeypatch.setattr(pce, "_send", lambda config, payload: sent.append(payload))
    return sent


# ---------------------------------------------------------------------------
# Provider derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("anthropic/claude-sonnet-4-6", "anthropic"),
        ("openai/gpt-5-5", "openai"),
        ("databricks-gpt-5-5", "databricks"),
        ("claude-opus-4-8", "anthropic"),
        ("gpt-5", "openai"),
        ("gemini-2.5-pro", "gemini"),
        ("qwen3-coder:cloud", "dashscope"),
        ("totally-unknown-model", "unknown"),
    ],
)
def test_derive_provider(model: str, provider: str) -> None:
    assert pce.derive_provider(model) == provider


# ---------------------------------------------------------------------------
# costCents rounding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("usd", "cents"),
    [
        (0.0, 0),
        (1.0, 100),
        (0.1234, 12),
        (0.126, 13),
        (0.004, 0),
        (7.8, 780),
    ],
)
def test_usd_to_cents(usd: float, cents: int) -> None:
    result = pce.usd_to_cents(usd)
    assert result == cents
    assert isinstance(result, int) and not isinstance(result, bool)


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


def test_build_cost_event_payload_shape() -> None:
    occurred = datetime(2026, 8, 22, 12, 0, 5, tzinfo=timezone.utc)
    payload = pce.build_cost_event(
        agent_id="polly",
        model="anthropic/claude-sonnet-4-6",
        cost_usd=0.05,
        occurred_at=occurred,
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=10,
    )
    assert payload == {
        "agentId": "polly",
        "provider": "anthropic",
        "model": "anthropic/claude-sonnet-4-6",
        "costCents": 5,
        "occurredAt": "2026-08-22T12:00:05+00:00",
        "inputTokens": 100,
        "outputTokens": 50,
        "cachedInputTokens": 10,
    }


def test_build_cost_event_normalizes_to_utc() -> None:
    # A non-UTC aware timestamp is converted, not emitted with its offset.
    from datetime import timedelta

    cdt = timezone(timedelta(hours=-5))
    occurred = datetime(2026, 8, 22, 7, 0, 5, tzinfo=cdt)
    payload = pce.build_cost_event(
        agent_id="polly",
        model="gpt-5",
        cost_usd=1.0,
        occurred_at=occurred,
    )
    assert payload["occurredAt"] == "2026-08-22T12:00:05+00:00"


# ---------------------------------------------------------------------------
# Config gate: off by default, all-or-nothing when enabled
# ---------------------------------------------------------------------------


def test_config_is_none_by_default() -> None:
    assert pce.load_paperclip_config() is None


def test_config_requires_core_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_PAPERCLIP_COST_REPORTING_ENABLED", "true")
    # Enabled but unconfigured -> still disabled (no URL to post to).
    assert pce.load_paperclip_config() is None


def test_config_loads_when_fully_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    config = pce.load_paperclip_config()
    assert config is not None
    assert config.cost_events_url == "http://paperclip.test/companies/co_123/cost-events"
    assert config.agent_id == "polly"
    assert config.api_token == "sekret"


def test_report_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture_sends(monkeypatch)
    pce.report_cost_event(
        model="anthropic/claude-sonnet-4-6",
        cost_usd=0.05,
        occurred_at=datetime.now(timezone.utc),
    )
    assert sent == []


def test_report_posts_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    sent = _capture_sends(monkeypatch)
    pce.report_cost_event(
        model="anthropic/claude-sonnet-4-6",
        cost_usd=0.05,
        occurred_at=datetime(2026, 8, 22, 12, 0, 5, tzinfo=timezone.utc),
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=10,
    )
    assert len(sent) == 1
    assert sent[0]["agentId"] == "polly"
    assert sent[0]["provider"] == "anthropic"
    assert sent[0]["costCents"] == 5


# ---------------------------------------------------------------------------
# Error swallowing: a dead Paperclip must never raise into the relay loop
# ---------------------------------------------------------------------------


def test_send_swallows_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    config = pce.load_paperclip_config()
    assert config is not None

    def _boom(*args: object, **kwargs: object) -> object:
        raise ConnectionError("paperclip unreachable")

    monkeypatch.setattr(pce.httpx, "post", _boom)
    # Must not raise.
    pce._send(config, {"agentId": "polly"})


def test_report_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(pce, "_submit", lambda task: task())

    def _boom(config: object, payload: object) -> None:
        raise RuntimeError("unexpected internal failure")

    monkeypatch.setattr(pce, "_send", _boom)
    # Even an unexpected failure inside the reporter is swallowed.
    pce.report_cost_event(
        model="gpt-5",
        cost_usd=1.0,
        occurred_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Hook: relay path (_accumulate_session_usage)
# ---------------------------------------------------------------------------


def test_relay_priced_turn_reports_cost_event(
    db_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    sent = _capture_sends(monkeypatch)
    store = SqlAlchemyConversationStore(db_uri)
    conv = store.create_conversation(title="relay", agent_id=_AGENT_ID)

    _accumulate_session_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 160,
                "cache_read_input_tokens": 10,
                "cost_usd": 0.05,
                "model": "anthropic/claude-sonnet-4-6",
            }
        },
        conv.id,
        store,
    )

    assert len(sent) == 1
    event = sent[0]
    assert event["agentId"] == "polly"
    assert event["provider"] == "anthropic"
    assert event["model"] == "anthropic/claude-sonnet-4-6"
    assert event["costCents"] == 5
    assert event["inputTokens"] == 100
    assert event["outputTokens"] == 50
    assert event["cachedInputTokens"] == 10
    occurred = str(event["occurredAt"])
    assert datetime.fromisoformat(occurred).tzinfo is not None

    # The ledger itself is unchanged by the reporter.
    stored = store.get_conversation(conv.id)
    assert stored is not None
    assert stored.session_usage["total_cost_usd"] == pytest.approx(0.05)
    assert stored.session_usage["input_tokens"] == 100


def test_relay_unpriced_turn_reports_nothing(db_uri: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    sent = _capture_sends(monkeypatch)
    store = SqlAlchemyConversationStore(db_uri)
    conv = store.create_conversation(title="unpriced", agent_id=_AGENT_ID)

    # No cost_usd and no resolvable model -> unpriced turn, no event.
    _accumulate_session_usage(
        {"usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}},
        conv.id,
        store,
    )
    assert sent == []


def test_relay_priced_turn_disabled_reports_nothing(
    db_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_sends(monkeypatch)
    store = SqlAlchemyConversationStore(db_uri)
    conv = store.create_conversation(title="disabled", agent_id=_AGENT_ID)

    _accumulate_session_usage(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "cost_usd": 0.05,
                "model": "anthropic/claude-sonnet-4-6",
            }
        },
        conv.id,
        store,
    )
    assert sent == []


# ---------------------------------------------------------------------------
# Hook: native path (_persist_native_cumulative_usage) — per-turn deltas
# ---------------------------------------------------------------------------


def test_native_cumulative_reports_per_turn_deltas(
    db_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    sent = _capture_sends(monkeypatch)
    store = SqlAlchemyConversationStore(db_uri)
    conv = store.create_conversation(title="native", agent_id=_AGENT_ID)

    _persist_native_cumulative_usage(
        conv.id,
        {
            "cumulative_cost_usd": 3.0,
            "cumulative_input_tokens": 1000,
            "cumulative_output_tokens": 200,
            "cumulative_cache_read_input_tokens": 400,
            "model": "claude-opus-4-8",
        },
        store,
    )
    _persist_native_cumulative_usage(
        conv.id,
        {"cumulative_cost_usd": 10.80, "model": "claude-opus-4-8"},
        store,
    )

    assert len(sent) == 2
    first, second = sent
    assert first["provider"] == "anthropic"
    assert first["model"] == "claude-opus-4-8"
    assert first["costCents"] == 300
    # The reported input total is split: non-cached input vs cache reads.
    assert first["inputTokens"] == 600
    assert first["cachedInputTokens"] == 400
    assert first["outputTokens"] == 200
    # Second report grew the cumulative total 3.00 -> 10.80: a 7.80 turn.
    assert second["costCents"] == 780
    assert second["inputTokens"] == 0
    assert second["outputTokens"] == 0


def test_native_replayed_total_reports_nothing(
    db_uri: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch)
    sent = _capture_sends(monkeypatch)
    store = SqlAlchemyConversationStore(db_uri)
    conv = store.create_conversation(title="replay", agent_id=_AGENT_ID)

    report = {"cumulative_cost_usd": 3.0, "model": "claude-opus-4-8"}
    _persist_native_cumulative_usage(conv.id, dict(report), store)
    _persist_native_cumulative_usage(conv.id, dict(report), store)

    # No cost growth on the replay -> no second event.
    assert len(sent) == 1
