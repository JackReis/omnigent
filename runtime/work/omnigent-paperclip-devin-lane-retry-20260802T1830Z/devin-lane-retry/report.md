# Bounded Devin Lane Read-Only Audit

## Result
This session is operating as the registered **Devin** lane with **Ringer** as the execution spine. The lane registry at `/Users/hermes/Vault/coordination/omnigent-dispatch/fleet/lane-registry.yaml` lists the Devin lane as registered under `paperclip` authority and `ringer` execution, and the active run artifact confirms that Ringer launched a `devin` process for this exact task. No repository files were modified, no Paperclip API calls were made, and no network access was attempted.

## Adapter Checks
| Adapter | Binary | Version / Path | Config Path | State Path |
|---|---|---|---|---|
| Devin | `/Users/hermes/.local/bin/devin` | `devin 3000.3.27 (0becb483)` | `~/.config/devin/config.json` | `~/.config/devin` |
| Cursor | `/Users/hermes/.local/bin/cursor-agent` | `2026.07.23-e383d2b` | `~/.cursor` (root state dir) | `~/.cursor/projects` |
| Ringer | `/Users/hermes/.local/bin/ringer` | usage-only invocation (no `-v`/`--version`) | `~/.ringer` | `~/.ringer` |

### Observed config metadata (non-secret keys only)
- `~/.config/devin/config.json` top-level keys: `devin`, `permissions`, `shell`, `theme_mode`, `version`  
  `version => 1`; `theme_mode => dark`; `permissions` contains `allow`.
- `~/.config/devin/mcp_config.json` top-level keys: `mcpServers`; registered server: `devin/deepwiki`.
- `~/.config/devin/cli/` directory is empty; `~/.config/devin/skills/` contains a `here-now` symlink.
- `~/.cursor/cli-config.json` top-level keys include `approvalMode`, `authInfo`, `model`, `permissions`, `sandbox`, `serverConfigCache`, `version`.
- `~/.cursor/mcp.json` top-level keys: `mcpServers`.
- `~/.cursor/argv.json` exists but is empty/malformed (JSON parse error).

## Lane Mapping
From `fleet/lane-registry.yaml`:

```yaml
devin:
  display_name: Devin
  lane_contract_version: 1.0.0
  adapter_version: 1.0.0
  policy_version: 1.0.0
  registrations: [paperclip, ringer]
  capabilities: [orchestration, environment_setup, cross_service_coordination]
  default_profile: planner
  omnigent_direct_allowed: false
  paths:
    executable: devin
    config: ~/.config/devin/config.json
    state: ~/.config/devin
  invocation:
    args: [--print, --permission-mode, accept-edits, --respect-workspace-trust, "false", --]
```

Runtime confirmation:
- Work directory: `/Users/hermes/Vault/coordination/omnigent-dispatch/runtime/work/omnigent-paperclip-devin-lane-retry-20260802T1830Z/devin-lane-retry`
- `worker.log` line 3: `[ringer.py] engine: devin`
- `~/.ringer/active-runs.json` shows a matching run:
  ```json
  {
    "omnigent-paperclip-devin-lane-retry-20260802T1830Z-20260802T182915Z-p10129": {
      "identity": "omnigent",
      "pid": 10129,
      "run_name": "omnigent-paperclip-devin-lane-retry-20260802T1830Z",
      "started_at": "2026-08-02T18:29:15.465534+00:00",
      "workdir": "/Users/hermes/Vault/coordination/omnigent-dispatch/runtime/work/omnigent-paperclip-devin-lane-retry-20260802T1830Z"
    }
  }
  ```
- `worker.log` launch command: `/Users/hermes/.local/bin/devin --print --permission-mode dangerous --respect-workspace-trust false -- <task>`

## Smoke Gate
- `devin --version` returned `0` with `devin 3000.3.27 (0becb483)`.
- `cursor-agent --version` returned `0` with `2026.07.23-e383d2b`.
- `ringer` binary is on `PATH`; `ringer --version` (or `ringer` with no subcommand) prints usage and exits `2`, indicating the CLI loads but requires a subcommand.
- `~/.ringer/` contains `active-runs.json`, `ringer.db`, `runs/`, `artifacts/`, `manifests/`, `receipts/`, and `hud.log`, showing a live Ringer state substrate.

## Workload
The assigned workload was a bounded read-only inspection: validate local Devin and Cursor adapter commands, inspect their config/state paths, read the lane registry, and confirm this task is running under the registered Devin lane. The only action taken was reading files and running non-destructive local commands (`which`, `--version`, `ls`, `python3` key extraction). The deliverable `report.md` is the only new file in the task directory (`worker.log` pre-existed).

## Governance
- Lane registry governance block: `authority: paperclip`, `execution_spine: ringer`, `omnigent_direct_bypass: denied_for_registered_lanes`.
- Devin lane: `registrations: [paperclip, ringer]`, `omnigent_direct_allowed: false`.
- These registry entries match the observed runtime: the task was launched by Ringer, the Devin binary is the engine, and the task name/path carries `omnigent-paperclip-devin-lane-retry`.
- No Paperclip API invocation occurred; authority was validated by registry registration only.

## Risks
1. **Invocation drift:** The actual launch used `--permission-mode dangerous`, while the registry `devin.invocation.args` specifies `accept-edits`. This is a deviation that could allow broader permissions than the registered lane policy expects.
2. **Cursor `argv.json` corruption:** `~/.cursor/argv.json` is empty/invalid JSON, which could break Cursor-agent argument parsing or state tracking.
3. **No dedicated version flag for Ringer:** `ringer --version` does not print a version; version tracking relies on file/source metadata.
4. **MCP server gap:** Devin `mcp_config.json` only registers `devin/deepwiki`; the registry references a richer ecosystem, but I did not verify connectivity (no network access).

## Next Adjustment
1. Reconcile the Devin invocation in `fleet/lane-registry.yaml` (currently `accept-edits`) with the actual Ringer launch template (`dangerous`) so the registry reflects the true permission mode, or vice versa.
2. Repair `~/.cursor/argv.json` (remove or populate valid JSON) to avoid Cursor-agent launch errors.
3. Add a `--version` or `version` subcommand to the Ringer wrapper so smoke checks can return a version string instead of usage text.
4. Re-run this audit after the fixes with the same command set to confirm the registry and runtime are byte-for-byte aligned.
