# Ringer Runbook

This is the current operating guide for running Ringer safely in the local
Paperclip/Omnigent fleet. It favors small, verifiable batches over unattended
fan-out.

## The short version

Use Ringer when work can be split into independent tasks and each task can leave
an artifact with an executable check. Keep ordinary queue work, approvals, and
status changes in Paperclip. Use Omnigent only as the routing front door; use
Ringer as the execution and receipt spine.

The reliable sequence is:

```text
write manifest → lint → baseline → run → inspect checks and artifacts
```

Do not skip the baseline. A check that passes before a worker runs does not
prove that the worker changed anything useful.

## Governance contract

Paperclip remains the authority for queue state, approvals, and issue status.
Ringer owns the run lifecycle: it writes and launches the manifest, controls
retries, evaluates verification checks, and preserves the audit record. Devin
and Cursor are execution lanes only; they do not create agents, spawn work,
reroute tasks, change scope, or close Paperclip work.

Every registered lane entry must declare:

- `owner: ringer` — Ringer owns the lane invocation and disposition.
- `allowed_scope: execute_assigned_task` — the lane may only perform its assigned task.
- `return_control_to: ringer` — the lane hands control back to Ringer.
- `return_control_on: [failure, ambiguity, out_of_scope]` — no lane self-reroutes or expands scope.

Ringer may make one additional attempt after a failed check, including the raw
failure output in the retry context. If that bounded retry fails, Ringer marks
the task `BLOCKED` and escalates it to the Paperclip issue owner or the Board;
it does not silently retry, reassign, or declare success.

## Choose the right path

| Situation | Best path |
|---|---|
| One sequential task or a normal queue update | Paperclip or the local agent directly |
| Two to four independent implementation tasks | Ringer swarm |
| Research or planning with independent alternatives | Ringer `planner` or `poly` profile |
| Implementation with independent file ownership | Ringer `coder` profile |
| Verification of an existing change | Ringer `review` profile |
| One named Devin or Cursor workflow | Registered Ringer lane, never a direct Omnigent bypass |

Ringer is not a replacement for a conversation. If a task needs tight,
sequential back-and-forth, keep it inline instead of forcing it into a swarm.

## Run a plain Ringer manifest

Use the checked-out Ringer entry point from its own repository or your installed
wrapper:

```bash
RINGER_ROOT=/absolute/path/to/ringer
RINGER="$RINGER_ROOT/ringer.py"

python3 "$RINGER" lint /absolute/path/to/manifest.json
python3 "$RINGER" run /absolute/path/to/manifest.json --baseline --no-dashboard
python3 "$RINGER" run /absolute/path/to/manifest.json --max-parallel 4
```

Use `--no-dashboard` for headless or scripted work. Omit it when you want
Ringside to open for live monitoring. A normal run opens or updates the local
Ringside view and writes run state, logs, and receipts under the configured
Ringer state directory.

For a safe plan check that does not spawn workers:

```bash
python3 "$RINGER" run /absolute/path/to/manifest.json --dry-run --no-dashboard
```

The local fleet defaults to a bounded fan-out. Keep `max_parallel` at the
smallest value that preserves useful independence; two is a good default for
the current Omnigent dispatcher and four is the upper bound for a deliberate
Ringer batch.

## Manifest shape that verifies work

Every task needs a self-contained `spec`, a `check` whose exit code is the
verdict, and preferably `expect_files`, `task_type`, and `verified` metadata.

```json
{
  "run_name": "docs-example",
  "workdir": "/tmp/ringer/docs-example",
  "max_parallel": 2,
  "tasks": [
    {
      "key": "write-readme",
      "engine": "codex",
      "task_type": "docs",
      "spec": "Write README.md with the requested sections and keep the file self-contained.",
      "check": "python3 -c 'from pathlib import Path; p=Path(\"README.md\"); assert p.is_file(), \"README.md missing\"; assert p.stat().st_size > 200, \"README.md is too short\"'",
      "expect_files": ["README.md"],
      "timeout_s": 900,
      "max_attempts": 2,
      "verified": "README.md exists and is non-empty enough to contain the requested documentation."
    }
  ]
}
```

Good checks explain their own failure. Prefer an assertion with a message or a
diff over a silent `exit 1`. The worker's summary is not evidence; the check is.

## Use the current Omnigent front door

The existing project is `omnigent-dispatch`. Its dispatcher keeps Paperclip as
authority and routes registered sibling lanes through Ringer:

```bash
cd /Users/hermes/Vault/coordination/omnigent-dispatch

./scripts/start_fleet_dispatcher.sh
python3 scripts/fleet_dispatch.py "Validate the fleet route" \
  --engines mock --dry-run
python3 scripts/fleet_dispatch.py "Compare two approaches" \
  --route --tag multi-model --dry-run
```

The route meanings are:

- `paperclip-native`: ordinary workflow and queue work.
- `omnigent-direct`: an explicitly requested single harness.
- `ringer-omnigent`: multi-agent, multi-model, poly, or registered-lane work.

For the registered lanes, use either the exact lane name or the current voice
aliases `devin`/`devon` and `cursor`/`curser`. The aliases only select the
registered lane; they do not bypass Paperclip governance.

## Devin and Cursor lanes

The lane registry is:

```text
fleet/lane-registry.yaml
```

Current adapter defaults are intentionally explicit:

| Lane | Executable | Config | State |
|---|---|---|---|
| Devin | `devin` | `~/.config/devin/config.json` | `~/.config/devin` |
| Cursor | `cursor-agent` | `~/.cursor` | `~/.cursor/projects` |

The registry also carries the invocation arguments that are propagated into a
generated manifest. Validate the registry before dispatching a lane:

```bash
cd /Users/hermes/Vault/coordination/omnigent-dispatch
.venv/bin/python - <<'PY'
from omnigent.fleet_dispatch import load_lane_registry

registry = load_lane_registry()
assert {"devin", "cursor"} <= registry.keys()
print("lane registry: PASS")
PY
```

Do not put Paperclip-owned runtime variables in adapter configuration. In
particular, `PAPERCLIP_RUN_SCRATCH_DIR` is reserved and must not appear under
an adapter `env` mapping. The dispatcher rejects it before a Ringer launch.

For the registered Devin lane, keep `--permission-mode dangerous` explicit in
both the registry and the Ringer engine config. Devin's non-interactive
`accept-edits` mode still rejects localhost Paperclip/API reads that require
confirmation; the explicit mode prevents a hidden per-run override. This does
not change governance: the task remains read-only by spec, Ringer owns the
lifecycle and receipt, Paperclip remains authority, and the lane cannot change
scope or disposition. Use this lane only with a bounded manifest whose check
enforces the expected artifact and whose prompt forbids mutations.

## Inspect a run

Read the run in this order:

1. The final verdict table in the terminal or Ringside.
2. The task's `check` output and raw worker log.
3. The expected artifact in the task directory.
4. The final receipt and manifest paths.
5. The local model/evaluation record when comparing engines.

Useful commands:

```bash
python3 "$RINGER" hud
python3 "$RINGER" models
python3 "$RINGER" db status
```

The local model scoreboard is evidence for routing decisions, not a promise
that a model will pass a new task. Audition a newly added model on low-stakes
work, then inspect its pass rate by task type before promoting it.

## Failure and retry policy

Ringer's useful retry is bounded: one retry with the raw failure output injected
into the prompt. If the second attempt fails, stop and repair the spec or the
check, mark the task `BLOCKED`, and escalate to the Paperclip issue owner or the
Board. Do not increase attempts or reroute ownership until a noisy or incorrect
check has been fixed and the escalation is resolved.

Use this triage order:

1. `lint` failure: fix the manifest before spending worker tokens.
2. Baseline failure: the check or starting tree is wrong; do not launch.
3. Worker failure with a clear check error: fix the artifact or rerun once.
4. Timeout or missing transcript: inspect the engine, host, and runner before
   blaming the task.
5. Missing artifact after PASS: treat it as a verification defect and preserve
   the raw run record.

For any failure, ambiguity, or out-of-scope request from Devin or Cursor, return
control to Ringer before taking another action. Ringer records the disposition;
Paperclip owns the issue state and the Board is the escalation path when no
issue owner is available.

Never convert a failed launch, unavailable runner, or evidence-free synthetic
card into a successful task disposition.

## Receipts and audit trail

Keep these outputs together:

- the exact manifest used;
- the lint and baseline output;
- each task's raw worker log;
- the final Ringer receipt and artifact report;
- the Paperclip issue or Beads identifier;
- a short disposition explaining PASS, FAIL, or BLOCKED.

For the current dispatcher, generated manifests and receipts live under:

```text
runtime/manifests/
runtime/receipts/
runtime/outbox/
runtime/vault/fleet-events/
```

The outbox is for retryable connector delivery. It is not a second source of
truth. Paperclip remains the coordination surface and Aegis remains
authoritative for work state.

## Anti-patterns

- Running a swarm for one sequential task.
- Using a worker's prose as the success signal.
- Running without `lint` and `--baseline`.
- Sharing one relative output file across parallel tasks.
- Hiding the real prompt in an external instruction-file pointer.
- Setting Paperclip runtime variables from an adapter config.
- Spawning unbounded retries when the check is wrong.
- Closing a task without preserving the raw failure output.

## Local verification

Run the focused configuration checks after changing the dispatcher or lane
registry:

```bash
cd /Users/hermes/Vault/coordination/omnigent-dispatch
.venv/bin/ruff check --select I001,RUF043,C405 \
  omnigent/fleet_dispatch.py fleet/tests/test_fleet_dispatch.py
.venv/bin/pytest -q fleet/tests/test_fleet_dispatch.py
```

The focused suite covers routing, lane compatibility, manifest propagation,
Devin/Cursor paths, spoken aliases, and reserved Paperclip environment
variables. For a broader change, add the relevant project test groups rather
than treating this focused suite as a complete system soak.
