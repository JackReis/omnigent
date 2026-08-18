# JAC-4173 Invocation Drift Fix

Date: 2026-08-02

## Result

The Devin invocation drift is fixed at the source. The registered lane,
canonical Ringer config, generated manifest, and executed command now all use:

```text
devin --print --permission-mode dangerous --respect-workspace-trust false -- <prompt>
```

Ringer lint, dry-run, the 24-test fleet-dispatch shard, and the bounded
JAC-4173 verification all passed. The worker artifact check passed on its first
attempt. The live report is `DEGRADED` because JAC-4173 is still `todo`, JAC-4000
has the same title and an active run, and no Paperclip agent named Devin exists.

## What changed

- Updated `fleet/lane-registry.yaml` so Devin's invocation is explicit and
  matches the working non-interactive adapter.
- Updated `runtime/ringer-devin-config.toml` so Ringer no longer needs a
  per-run dangerous-mode override.
- Updated `fleet/tests/test_fleet_dispatch.py` to lock the propagated command.
- Documented the localhost/API confirmation rationale and unchanged governance
  in `docs/RINGER_RUNBOOK.md`.
- Added the clean verification manifest
  `runtime/manifests/omnigent-paperclip-jac4173-devin-invocation-fixed-20260802T1905Z.ringer.json`.

Governance is unchanged: Paperclip remains authority; Ringer owns lifecycle,
retry, verification, and receipts; Devin remains execution-only; direct
Omnigent bypass remains denied; and the run returned control to Ringer on
ambiguity.

## Evidence

- Ringer run: `omnigent-paperclip-jac4173-devin-invocation-fixed-20260802T1905Z-20260802T185056Z-p43902`
- Worker report: `runtime/work/omnigent-paperclip-jac4173-devin-invocation-fixed-20260802T1905Z/jac4173-devin-invocation-fixed/report.md`
- Worker log: `runtime/work/omnigent-paperclip-jac4173-devin-invocation-fixed-20260802T1905Z/jac4173-devin-invocation-fixed/worker.log`
- Receipt: `runtime/ringer-state/runs/omnigent-paperclip-jac4173-devin-invocation-fixed-20260802T1905Z-20260802T185056Z-p43902.json`
- Verification: `lint: clean`, dry-run PASS, `24 passed`, task verdict PASS, one attempt.

## Remaining flags

1. **Paperclip 404:** the prior retry receipt recorded
   `skipped_preflight_error` / `HTTP 404` for the synthetic
   `JAC-LANE-RUN-20260802` projection target. Verify the target and base
   URL/routing before enabling that projection in production.
2. **State writer:** the prior outbox report recorded a Ringer state-writer
   `ENOENT` after PASS. The fixed receipt has no new warning, but persistence
   should still be exercised and checked for atomic writes.
3. **Unexpected projection side effect:** the fixed receipt records
   `JAC-4173` with outcome `created` despite the task being read-only. Confirm
   whether this is an intended Ringer projection or an authority-boundary bug;
   do not run another workload until reconciled.
4. **Queue identity ambiguity:** reconcile `JAC-4173` versus active `JAC-4000`
   and register/route through a Paperclip Devin agent identity before further
   execution.

## Recommended next steps

Keep the invocation fix. Repair the projection target and state writer, then
reconcile the duplicate queue item and Devin identity before dispatching any
additional real workload.
