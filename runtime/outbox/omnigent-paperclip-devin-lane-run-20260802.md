# Ringer Devin Lane Run

Date: 2026-08-02

## Disposition

PASS on the bounded retry. Ringer owned the run and launched the registered
Devin engine; the executable report check passed on the first retry attempt.

## Sequence

1. Lane registry validation: PASS for Devin and Cursor; contract, adapter, and
   policy versions are `1.0.0`, and both lanes are registered with Paperclip and
   Ringer.
2. Adapter preflight: PASS. `devin` is `3000.3.27`; `cursor-agent` is
   `2026.07.23-e383d2b`; configured paths exist.
3. Ringer lint: PASS for both manifests.
4. Ringer dry-run: PASS; the installed CLI does not support the runbook's
   older `--baseline` flag, so the supported dry-run was used as the no-spawn
   plan gate.
5. Initial run: FAIL after two bounded attempts because Devin's
   non-interactive `accept-edits` mode rejected required tool confirmations.
6. Retry: PASS in 77.9 seconds; `report.md` exists, exceeds the size threshold,
   and contains every required verification heading.

## Key Findings

- The expected architecture is confirmed: Paperclip authority → Ringer
  execution spine → Devin lane worker.
- The registry says Devin should use `--permission-mode accept-edits`, but the
  only non-interactive launch that completed used `dangerous`; this is an
  invocation-policy drift that should be reconciled before production use.
- Cursor's `~/.cursor/argv.json` is empty/invalid JSON and should be repaired
  before selecting Cursor as the worker lane.
- Ringer emitted `Paperclip ... skipped_preflight_error: HTTP 404` and a state
  writer `ENOENT` after the successful run; the worker result and JSONL eval row
  still record PASS, but those integration warnings need follow-up.

## Evidence

- Manifest: `runtime/manifests/omnigent-paperclip-devin-lane-retry-20260802T1830Z.ringer.json`
- Config: `runtime/ringer-devin-danger-config.toml`
- Devin report: `runtime/work/omnigent-paperclip-devin-lane-retry-20260802T1830Z/devin-lane-retry/report.md`
- Worker log: `runtime/work/omnigent-paperclip-devin-lane-retry-20260802T1830Z/devin-lane-retry/worker.log`
- Ringer receipt: `runtime/ringer-state/runs/omnigent-paperclip-devin-lane-retry-20260802T1830Z-20260802T182915Z-p10129.json`
- Ringer HTML report: `runtime/ringer-state/artifacts/omnigent-paperclip-devin-lane-retry-20260802T1830Z-20260802T182915Z-p10129-report.html`
- Initial failed run: `runtime/manifests/omnigent-paperclip-devin-lane-run-20260802T1828Z.ringer.json`

## Recommended Adjustments

1. Make the Devin registry invocation and Ringer config agree on the intended
   non-interactive permission mode; do not leave `dangerous` implicit.
2. Repair or remove invalid Cursor `argv.json`, then rerun the same smoke gate.
3. Investigate the Paperclip preflight 404 and Ringer state-writer `ENOENT`
   before treating this lane as fully production-ready.
