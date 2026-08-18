# Paperclip 404 and Ringer State-Writer Remediation

Date: 2026-08-03

## Result

Both remaining run flags are resolved for the affected read-only lane flow.

- Synthetic projection IDs were removed from the lane probe, lane run, and
  retry manifests. Those IDs do not exist in the live Paperclip instance and
  were the direct cause of the post-run `HTTP 404` warning.
- The live Paperclip base route is `http://127.0.0.1:3101/` and returned
  `200`. The real `JAC-4173` issue returned `200`; the synthetic lane ID
  returned `404`, confirming an invalid reference rather than a routing fault.
- Ringer state writes now use the existing unique-temp-file atomic writer
  instead of a shared `<run>.json.tmp` path. This removes the concurrent flush
  race that could produce `ENOENT` during replacement.
- Final report state publication uses the same atomic writer, so the final
  `report_ready` update follows the same safe path.

## Verification

- `test_artifact_endstate.py`: 7 passed, including concurrent flush coverage.
- Lane manifests: all three cleaned manifests lint clean.
- Baseline run: expected failure because `report.md` is intentionally absent
  before the worker runs; no worker was spawned in baseline mode.
- Safe Ringer lane probe: PASS, one attempt, `report_ready=true`.
- The verification receipt contains no new `ENOENT`, `HTTP 404`, or projection
  warning.

## Files Changed

- `/Users/hermes/ringer/ringer.py`
- `/Users/hermes/ringer/tests/test_artifact_endstate.py`
- `runtime/manifests/omnigent-paperclip-lane-probe-20260802T1822Z.ringer.json`
- `runtime/manifests/omnigent-paperclip-devin-lane-run-20260802T1828Z.ringer.json`
- `runtime/manifests/omnigent-paperclip-devin-lane-retry-20260802T1830Z.ringer.json`

## Follow-Ups

The live probe surfaced an existing governance inconsistency: six older
registered lanes still set `omnigent_direct_allowed: true` while the registry
policy says direct bypass is denied for registered lanes. That is separate from
the two repaired flags and should be reconciled before broader dispatch.
