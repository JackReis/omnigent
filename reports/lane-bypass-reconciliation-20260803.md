# Lane Bypass Reconciliation

Date: 2026-08-03

## Result

All registered execution lanes now honor the top-level Ringer governance rule:
`omnigent_direct_bypass: denied_for_registered_lanes`.

The six legacy lanes identified by the prior probe—Hermes, Claude, Codex, Kimi,
Pi, and OpenCode—now have `omnigent_direct_allowed: false`, matching Devin and
Cursor. No per-lane exception was added.

## Verification

- Registry inspection reports `false` for all eight registered lanes.
- Added a regression test requiring every registered lane to deny direct
  Omnigent bypass.
- Fleet dispatch shard: `25 passed`.
- The system Python 3.9 failure was environment-only (`typing.TypeAlias` is
  unavailable); rerunning with the project `.venv` passed.

## Follow-Up

Continue routing registered lanes through Paperclip and Ringer. Keep any
break-glass path separate, disabled by default, explicitly approved, and
time-bound rather than re-enabling a lane-level bypass.
