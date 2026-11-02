"""Run isolated guard-removal mutations; never modify the working source tree."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "integrations/slack/src"
SERVICE_TEST = "integrations/slack/tests/test_service.py::"
SCOPE_TEST = SERVICE_TEST + "test_handoff_callback_scope"
STALE_TEST = SERVICE_TEST + "test_handoff_stale_callback"
RESTART_TEST = SERVICE_TEST + "test_handoff_restart_never_resends_original"
TERMINAL_TEST = SERVICE_TEST + "test_handoff_source_observation_is_not_acceptance"
PARTIAL_TEST = SERVICE_TEST + "test_handoff_partial_response_blocks_followup"
RETRY_TEST = (
    "integrations/slack/tests/test_omnigent.py::test_handoff_runner_loss_after_submit_cannot_retry"
)

# Each edit removes a safety boundary while leaving the adapter operational.
MUTATIONS: dict[str, tuple[list[tuple[str, str, str]], str]] = {
    "actor-binding": (
        [
            ("service.py", "record.owner_user_id != clicker", "False"),
            (
                "elicitation.py",
                "if target != ClickTarget(binding.owner_user_id, session_id, elicitation_id):",
                "if target is None or target.session_id != session_id "
                "or target.elicitation_id != elicitation_id:",
            ),
            ("elicitation.py", '            "user": {"id": binding.owner_user_id},\n', ""),
        ],
        SCOPE_TEST,
    ),
    "thread-binding": (
        [
            ("elicitation.py", ', "thread_ts": binding.key.thread_ts', ""),
        ],
        SCOPE_TEST,
    ),
    "card-binding": (
        [
            (
                "elicitation.py",
                '"message": {"ts": binding.card_ts, "thread_ts": binding.key.thread_ts}',
                '"message": {"thread_ts": binding.key.thread_ts}',
            ),
            (
                "elicitation.py",
                '"container": {"message_ts": binding.card_ts, '
                '"channel_id": binding.key.channel_id}',
                '"container": {"channel_id": binding.key.channel_id}',
            ),
        ],
        SCOPE_TEST,
    ),
    "expiry-binding": (
        [
            ("elicitation.py", " or time.monotonic() >= binding.expires_at", ""),
        ],
        STALE_TEST,
    ),
    "durable-reservation": (
        [
            ("store.py", "WHERE slack_turn_observations.state = 'source_terminal'", "WHERE 1 = 1"),
        ],
        RESTART_TEST,
    ),
    "runner-retry": (
        [
            (
                "omnigent.py",
                "if submitted:\n                    raise StreamInterruptedError(",
                "if False:\n                    raise StreamInterruptedError(",
            ),
        ],
        RETRY_TEST,
    ),
    "eof-is-terminal": (
        [
            (
                "service.py",
                "state.source_terminal\n                    and not state.errored",
                "True\n                    and not state.errored",
            ),
        ],
        TERMINAL_TEST,
    ),
    "response-is-whole-turn": (
        [
            (
                "service.py",
                '        if event_type == "session.status":\n',
                '        if event_type == "response.completed":\n'
                "            state.source_terminal = True\n"
                '        if event_type == "session.status":\n',
            ),
        ],
        PARTIAL_TEST,
    ),
    "stale-terminal-after-running": (
        [("service.py", "                state.source_terminal = False\n", "")],
        PARTIAL_TEST,
    ),
    "idle-response-correlation": (
        [("service.py", "            and response_id == state.open_response_id\n", "")],
        PARTIAL_TEST,
    ),
}


def run_tests(source: Path, tests: list[str]) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONPATH": str(source), "PYTHONDONTWRITEBYTECODE": "1"}
    probe = subprocess.run(
        [sys.executable, "-c", "import omnigent_slack; print(omnigent_slack.__file__)"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    if not probe.stdout.strip().startswith(str(source)):
        raise RuntimeError("Mutation isolation failed: imported working-tree source")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "-x", *tests],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )


def main() -> int:
    baseline = run_tests(SOURCE, sorted({test for _edits, test in MUTATIONS.values()}))
    if baseline.returncode:
        print(baseline.stdout, baseline.stderr)
        return 1
    print("Baseline behavioral guards passed")
    for name, (edits, test) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix="omnigent-slack-mutant-") as directory:
            mutant = Path(directory) / "src"
            shutil.copytree(SOURCE, mutant, ignore=shutil.ignore_patterns("__pycache__"))
            for filename, before, after in edits:
                path = mutant / "omnigent_slack" / filename
                content = path.read_text()
                if content.count(before) != 1:
                    raise RuntimeError(f"{name}: expected one guard match in {filename}")
                path.write_text(content.replace(before, after))
            result = run_tests(mutant, [test])
            failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
            if (
                result.returncode != 1
                or not failures
                or not any(
                    marker in result.stdout for marker in ("AssertionError", "DID NOT RAISE")
                )
            ):
                print(f"SURVIVED/INVALID: {name}\n{result.stdout}\n{result.stderr}")
                return 1
            print(f"KILLED {name}: {failures[0]}")
    print(f"All {len(MUTATIONS)} guard-removal mutations killed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
