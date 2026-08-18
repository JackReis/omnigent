# Lane-Contract Smoke Test — Paperclip/Omnigent Fleet

## Result

The **Devin** and **Cursor** lane records in `fleet/lane-registry.yaml` are **internally consistent** with each other and with the top-level governance block. Version fields align, capability declarations are mirrored in `capability_mapping`, both lanes are registered with the same authorities, both disallow Omnigent direct bypass, and both define executable/config/state/invocation metadata.

One cross-lane inconsistency is visible: the top-level `omnigent_direct_bypass: denied_for_registered_lanes` is honored by Devin and Cursor (`omnigent_direct_allowed: false`) but not by the other registered lanes (Hermes, Claude, Codex, Kimi, Pi, OpenCode all set `omnigent_direct_allowed: true`). That is outside the scope of this lane smoke test but is flagged below as a fleet-level governance risk.

## Devin Lane

```yaml
lanes:
  devin:
    display_name: Devin
    lane_contract_version: 1.0.0
    adapter_version: 1.0.0
    policy_version: 1.0.0
    registrations: [paperclip, ringer]
    capabilities: [orchestration, environment_setup, cross_service_coordination]
    capability_mapping:
      contract_version: 1.0.0
      capabilities: [orchestration, environment_setup, cross_service_coordination]
    default_profile: planner
    omnigent_direct_allowed: false
    governance:
      owner: ringer
      allowed_scope: execute_assigned_task
      return_control_to: ringer
      return_control_on: [failure, ambiguity, out_of_scope]
    paths:
      executable: devin
      config: ~/.config/devin/config.json
      state: ~/.config/devin
    invocation:
      args: [--print, --permission-mode, dangerous, --respect-workspace-trust, "false", --]
```

**Consistency evidence:**

- `lane_contract_version`, `adapter_version`, and `policy_version` are all `1.0.0`.
- `capabilities` and `capability_mapping.capabilities` are identical: `[orchestration, environment_setup, cross_service_coordination]`.
- `capability_mapping.contract_version` equals `lane_contract_version`.
- `registrations` includes both `paperclip` and `ringer`, matching the top-level `authority: paperclip` and `execution_spine: ringer`.
- `omnigent_direct_allowed: false` matches the top-level `omnigent_direct_bypass: denied_for_registered_lanes` for a registered lane.
- `default_profile: planner` is appropriate for the declared orchestration/cross-service capabilities.
- Governance fields (`owner`, `allowed_scope`, `return_control_to`, `return_control_on`) are present and consistent with the other lanes.

**Path/invocation notes:**

- `paths.executable` is `devin` (bare command, relies on `PATH`).
- `paths.config` is `~/.config/devin/config.json` (file).
- `paths.state` is `~/.config/devin` (directory, the parent of the config file).
- `invocation.args` includes `--permission-mode dangerous` and `--respect-workspace-trust false`, which the inline comment states is explicit so generated manifests match the working Ringer adapter.

## Cursor Lane

```yaml
lanes:
  cursor:
    display_name: Cursor
    lane_contract_version: 1.0.0
    adapter_version: 1.0.0
    policy_version: 1.0.0
    registrations: [paperclip, ringer]
    capabilities: [editor, refactor, coding, testing, linting]
    capability_mapping:
      contract_version: 1.0.0
      capabilities: [editor, refactor, coding, testing, linting]
    default_profile: coder
    omnigent_direct_allowed: false
    governance:
      owner: ringer
      allowed_scope: execute_assigned_task
      return_control_to: ringer
      return_control_on: [failure, ambiguity, out_of_scope]
    paths:
      executable: cursor-agent
      config: ~/.cursor
      state: ~/.cursor/projects
    invocation:
      args: [--print, --output-format, json, --trust]
```

**Consistency evidence:**

- `lane_contract_version`, `adapter_version`, and `policy_version` are all `1.0.0`.
- `capabilities` and `capability_mapping.capabilities` are identical: `[editor, refactor, coding, testing, linting]`.
- `capability_mapping.contract_version` equals `lane_contract_version`.
- `registrations` includes `paperclip` and `ringer`.
- `omnigent_direct_allowed: false` matches the top-level `omnigent_direct_bypass: denied_for_registered_lanes`.
- `default_profile: coder` is appropriate for the declared editor/coding capabilities.
- Governance fields match the standard pattern.

**Path/invocation notes:**

- `paths.executable` is `cursor-agent` (bare command, relies on `PATH`).
- `paths.config` is `~/.cursor` (directory, not a file).
- `paths.state` is `~/.cursor/projects` (directory).
- `invocation.args` uses `--print --output-format json --trust`, a more constrained pattern than Devin and consistent with a read-only output smoke-test profile.

## Governance

Top-level governance from `fleet/lane-registry.yaml`:

```yaml
governance:
  authority: paperclip
  execution_spine: ringer
  lifecycle_owner: ringer
  registered_lane_scope: execution_only
  omnigent_direct_bypass: denied_for_registered_lanes
  retry:
    max_additional_attempts: 1
    on_exhaustion: blocked
  escalation: paperclip_issue_owner_or_board
```

The Devin and Cursor lanes are consistent with this block:

- They are `registered` with both `paperclip` and `ringer`.
- `omnigent_direct_allowed: false` implements `denied_for_registered_lanes`.
- `allowed_scope: execute_assigned_task` matches `registered_lane_scope: execution_only`.
- `return_control_to: ringer` and `return_control_on: [failure, ambiguity, out_of_scope]` mirror the `execution_spine` / `lifecycle_owner`.
- `retry.on_exhaustion: blocked` is consistent with a controlled, non-escalating retry policy.

## Risks

1. **Fleet-wide `omnigent_direct_allowed` policy drift.** Top-level policy is `denied_for_registered_lanes`, but Hermes, Claude, Codex, Kimi, Pi, and OpenCode all set `omnigent_direct_allowed: true` despite being registered. Only Devin and Cursor comply. This is a policy enforcement gap, not a Devin/Cursor defect.
2. **Bare executable names.** `devin` and `cursor-agent` are not absolute paths. Resolution depends on `PATH`, which can vary by host and session. A smoke test cannot confirm the binaries are actually present or named correctly.
3. **Config vs. state path semantics differ between lanes.** Devin `config` is a file (`~/.config/devin/config.json`) and `state` is its parent directory. Cursor `config` and `state` are both directories. The registry does not document whether `config` should be a file or directory, which could confuse adapters.
4. **Devin invocation uses `dangerous` permission mode.** The `args` include `--permission-mode dangerous` and `--respect-workspace-trust false`. The inline comment (lines 138-140) explains this is deliberate for read-only queue checks, but it is a high-trust profile and should be reviewed if the lane is used for more than read-only work.
5. **No validation timestamp or health metadata.** The registry does not record when it was last validated, by which process, or the result of the last smoke test. Future audits cannot tell whether the file is stale.
6. **Top-level `version: 1` vs. lane `*_version: 1.0.0`.** The registry uses an integer `1` at the top but semantic versions for each lane. This could signal a schema-version convention mismatch or an intentional distinction, but it is not documented in the file.
7. **Cursor `executable: cursor-agent` name uncertainty.** The canonical Cursor CLI is commonly invoked as `cursor` or `cursor-agent` depending on installation. The registry assumes `cursor-agent`; a PATH check on the host is the only way to verify the name is correct.

## Next Adjustment

1. **Reconcile `omnigent_direct_allowed` across all lanes** or add per-lane `omnigent_direct_allowed` exception annotations explaining why Hermes/Claude/Codex/Kimi/Pi/OpenCode are allowed to bypass the top-level `denied_for_registered_lanes` policy.
2. **Normalize the top-level `version` field** to `1.0.0` or document the convention that `version` is the registry schema major version while lane fields use semantic versioning.
3. **Make `paths.executable` absolute or add a PATH verification step** to the lane smoke test so execution can be validated on each host.
4. **Document and align `paths.config` semantics** — whether it must be a file, directory, or either — and adjust Devin or Cursor to match the chosen convention.
5. **Scope Devin invocation permissions** to a less privileged mode if the lane’s operational role is read-only queue checks; reserve `dangerous` for an explicit, opt-in task profile.
6. **Add `last_validated` / `validated_by` / `validation_result` metadata** to the registry or an external sidecar so each smoke test leaves durable evidence.
7. **Verify `cursor-agent` binary name and location** on the target host; if the binary is `cursor`, update the `executable` value before the lane is dispatched.
