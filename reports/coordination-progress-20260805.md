# Fleet Coordination Progress — 2026-08-05

## Omnigent dispatcher

- Located the real agent at `omnigent-dispatch/fleet/fleet-dispatcher.yaml`.
- The original `agent path not found` condition came from invoking the relative
  path outside the project root.
- Fixed the CLI wrapper so an omitted `--model` uses the configured Kimi K3
  default for direct dispatches while routed tasks retain automatic selection.
- Fixed mock manifests to omit model metadata, which the mock engine cannot
  consume.
- Mock dry-run passed: `omnigent-codex-path-recovery-20260805T211730Z`.
- Heavy-route dry-run passed and emitted `deepseek-v4-flash`:
  `omnigent-paperclip-planner-20260805T211730Z`.
- No live model call was made, so no credential or spend approval was needed.

## Ringer

- Ringside HUD is listening on port 8700 and `/api/runs` returned HTTP 200.
- Ringside reported `active: {}` and no `ringer.py run`, Kimi worker, or fleet
  dispatcher process remained after the probes.
- Paperclip responded on port 3101 after retrying with a 10-second timeout.
- The checkout at `/Users/hermes/ringer` is in an in-progress rebase on detached
  `HEAD`; unresolved files are `dashboard/ringside.html` and
  `registry/model-identity.toml`.
- Self-update safely fetched and recorded: three commits behind, blocked because
  the checkout is detached rather than on `main`.
- No rebase abort, reset, conflict resolution, restart, or process termination
  was performed. Choosing conflict sides or aborting the rebase requires owner
  approval because the checkout contains extensive staged work.

## Fleet/context

- `fleet/fleet-dispatcher.yaml` already carries the requested routing policy:
  OllamaCloud-powered Hermes with Kimi K3 by default, DeepSeek V4 Flash for
  heavier work, and conditional Ringer/Devin/Cursor routes.
- `docs/FLEET_DISPATCH_SETUP.md` now documents the absolute-path invocation and
  model-selection behavior.
- Focused dispatcher tests pass: 27 passed.

## Remaining approval

Approve one of these Ringer recovery paths before any mutation:

1. Abort the stale rebase after exporting a full patch backup, then return the
   checkout to its pre-rebase state.
2. Resolve both conflicts explicitly, run the Ringer test suite, and continue
   the rebase.

Until then, keep the current checkout and live HUD untouched.
