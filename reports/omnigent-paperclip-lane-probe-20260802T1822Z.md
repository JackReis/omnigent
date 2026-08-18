# Devin Lane Probe

## Disposition

- **Result:** PASS
- **Run:** `omnigent-paperclip-lane-probe-20260802T1822Z-20260802T182409Z-p94819`
- **Lane:** Devin, registered through Ringer
- **Attempts:** 1
- **Elapsed:** 62.6 seconds
- **Risk:** Low
- **Paperclip issue marker:** `JAC-LANE-PROBE-20260802`

## Validation

- Devin executable and config paths exist; Devin reports version `3000.3.22`.
- Cursor executable and state paths exist; Cursor reports version `2026.07.23-e383d2b`.
- Both lanes are contract, adapter, and policy version `1.0.0`.
- Registry loading and compatibility checks pass.
- Focused fleet-dispatch tests pass: `23 passed`.
- Ringer lint passes: `1 tasks`.
- Manual baseline passes: `report.md` was absent before launch.

## What Ran

Devin performed a read-only inspection of `fleet/lane-registry.yaml` and wrote
the verified report to the task directory. The task prohibited Paperclip API
calls, issue updates, agent creation, service restarts, secret access, and
network access. Ringer ran with `max_parallel: 1`, `full_access: false`, and
its built-in bounded retry behavior.

## Findings

- Devin and Cursor lane metadata is internally consistent.
- Paperclip remains the authority and Ringer remains the execution spine.
- Both new lanes correctly set `omnigent_direct_allowed: false`.
- Registry-wide governance has an existing ambiguity: six older registered
  lanes still set `omnigent_direct_allowed: true` despite the top-level
  `denied_for_registered_lanes` wording.
- Relative executable/config/state paths depend on correct `PATH` and home
  expansion; the targeted host checks passed.

## Caveat

Ringer printed `Paperclip JAC-LANE-PROBE-20260802: skipped_preflight_error:
HTTP 404` after the worker passed. This did not change the task verdict and no
Paperclip mutation was attempted. The checked-in Ringer build also does not
support the runbook's documented `--baseline` flag, so the baseline was
performed explicitly by confirming the expected report was absent before run.

## Recommended Next Adjustment

Clarify whether `omnigent_direct_bypass: denied_for_registered_lanes` applies
to every registered lane; if it does, align the six older lane records or add
an explicit exception field before enforcing the rule fleet-wide.
