import asyncio
from pathlib import Path

import pytest
from omnigent_slack.models import ThreadKey, UserConfig
from omnigent_slack.store import SQLiteStore


async def test_store_persists_thread_session(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "store.sqlite3")
    await store.initialize()

    key = ThreadKey(team_id="T1", channel_id="C1", thread_ts="100.1")
    assert await store.get_session(key) is None

    await store.upsert_session(
        key,
        "conv_1",
        "title",
        owner_user_id="U1",
        host_id="host_a",
    )
    record = await store.get_session(key)
    assert record is not None
    assert record.session_id == "conv_1"
    assert record.owner_user_id == "U1"
    assert record.host_id == "host_a"

    await store.upsert_session(key, "conv_2", "title", owner_user_id="U1")
    record = await store.get_session(key)
    assert record is not None
    assert record.session_id == "conv_2"


async def test_store_user_config_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "store.sqlite3")
    await store.initialize()

    assert await store.get_user_config("T1", "U1") is None

    config = UserConfig(
        agent_id="ag_1",
        agent_name="Helper",
        workspace="/home/me/project",
        host_id="host_a",
        host_name="Host A",
    )
    await store.upsert_user_config("T1", "U1", config)
    assert await store.get_user_config("T1", "U1") == config

    # Upsert overwrites and host may be cleared back to "any".
    updated = UserConfig(
        agent_id="ag_2",
        agent_name="Other",
        workspace="/tmp/ws",
    )
    await store.upsert_user_config("T1", "U1", updated)
    assert await store.get_user_config("T1", "U1") == updated
    # A different user in the same workspace is isolated.
    assert await store.get_user_config("T1", "U2") is None


async def test_store_claim_event_dedupes(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "store.sqlite3")
    await store.initialize()

    assert await store.claim_event("Ev1") is True
    assert await store.claim_event("Ev1") is False
    assert await store.claim_event(None) is True


async def test_store_unclaim_event_allows_reclaim(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "store.sqlite3")
    await store.initialize()

    assert await store.claim_event("Ev1") is True
    # Releasing the claim lets the same event id be processed again.
    await store.unclaim_event("Ev1")
    assert await store.claim_event("Ev1") is True
    # A no-op without an id, and harmless on an unknown id.
    await store.unclaim_event(None)
    await store.unclaim_event("never-seen")


@pytest.mark.parametrize(
    "state", ["reserved", "session_known", "submitting", "observing", "unknown"]
)
async def test_turn_observation_survives_restart_without_retry(tmp_path: Path, state: str) -> None:
    path = tmp_path / "store.sqlite3"
    store = SQLiteStore(path)
    await store.initialize()
    key = ThreadKey("T1", "C1", "100.1")
    run_id = await store.reserve_turn(key, "U1")
    assert run_id
    await store.observe_turn(
        key, run_id, state, session_id="original", native_response_id="resp_1"
    )
    reopened = SQLiteStore(path)
    await reopened.initialize()
    assert await reopened.reserve_turn(key, "U1") is None
    assert await reopened.reserve_turn(key, "U2") is None
    observation = await reopened.get_turn_observation(key)
    assert observation
    assert observation.run_id == run_id
    assert observation.session_id == "original"
    assert observation.native_response_id == "resp_1"
    assert observation.state == state
    assert observation.acceptance == "unknown"
    await reopened.observe_turn(key, "stale-run", "source_terminal")
    assert await reopened.get_turn_observation(key) == observation


async def test_source_terminal_frees_thread_without_acceptance(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "store.sqlite3")
    await store.initialize()
    key = ThreadKey("T1", "C1", "100.1")
    first = await store.reserve_turn(key, "U1")
    await store.observe_turn(key, first, "source_terminal", session_id="original")
    observation = await store.get_turn_observation(key)
    assert observation and observation.acceptance == "unknown"
    assert await store.reserve_turn(key, "U2") is None
    second = await store.reserve_turn(key, "U1")
    assert second and second != first
    await store.observe_turn(key, first, "source_terminal")
    assert await store.reserve_turn(key, "U1") is None


async def test_turn_reservation_is_atomic_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "store.sqlite3"
    store = SQLiteStore(path)
    await store.initialize()
    key = ThreadKey("T1", "C1", "100.1")
    reservations = await asyncio.gather(
        *(SQLiteStore(path).reserve_turn(key, "U1") for _ in range(8))
    )
    assert sum(value is not None for value in reservations) == 1
    assert await store.reserve_turn(ThreadKey("T2", "C1", "100.1"), "U1")
    assert await store.reserve_turn(ThreadKey("T1", "D1", "100.1"), "U1")
