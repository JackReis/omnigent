# Ringer Configuration Enhancement Audit

Date: 2026-08-02

## Scope

- Preserved Paperclip as the authority and Ringer as the execution spine.
- Added explicit Devin and Cursor adapter paths and invocation defaults to the lane registry.
- Added spoken-name aliases for `devon` and `curser` so voice dispatch reaches the registered lanes.
- Added validation that rejects `PAPERCLIP_RUN_SCRATCH_DIR` in adapter configuration before launch.
- Kept adapter environment injection empty by default; no reserved Paperclip runtime variable is written to manifests.

## Verification

- YAML parsing: `fleet/fleet-dispatcher.yaml` and `fleet/lane-registry.yaml` load successfully.
- Focused test suite: 22 passed.
- Mock manifest execution: PASS for the Cursor lane.
- Ruff: existing repository style findings remain outside this focused change; touched test formatting was corrected.
