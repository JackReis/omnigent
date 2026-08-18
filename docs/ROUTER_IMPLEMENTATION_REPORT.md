# Paperclip–Omnigent Fleet Router

## Outcome

The `Omnigent Router` Paperclip role now has three deterministic execution paths:

1. `paperclip-native` for normal workflow, queue, status, and approval work.
2. `omnigent-direct` for explicit single-harness work.
3. `ringer-omnigent` for meta-harness, multi-model, multi-agent, Ringer, or Poly work.

The shared lane registry in `fleet/lane-registry.yaml` registers Hermes, Claude,
Codex, Kimi, Pi, OpenCode, Devin, and Cursor with both Paperclip and Ringer.
Devin and Cursor are protected sibling lanes: capability requests for either
lane always select `ringer-omnigent`, carry Paperclip authority, and set
`direct_omnigent_bypass` to false in the generated manifest.

Ringer-over-Omnigent supports durable profiles: `poly`, `planner`, `coder`, and `review`. Each profile identifies its orchestrator and harness without volatile agent IDs.

The lane registry stores three independent versions per lane: `lane_contract_version`,
`adapter_version`, and `policy_version`. Capability mappings explicitly reference
the lane contract version. Legacy entries without these fields normalize to
baseline `1.0.0`; unsupported major versions fail closed with a clear error.

## Contract and Evidence

Every route emits `fleet-handoff/v1` with task inputs, Paperclip/Beads authority references, decision reason, expected output, evidence paths, and Paperclip-native fallback. Policy decisions, dispatches, completions, and failures also emit idempotent `fleet-service-update/v1` records.

Each service update is written to a Vault-backed Markdown record and a retryable JSON outbox for Holographic, Honcho, Hindsight, OpenBrain1, Gbrain, and the Vaults. Connector delivery remains queued with exponential-backoff metadata until a service adapter acknowledges it; evidence is never dropped.

## Paperclip Setup

Create or update the Paperclip agent named `Omnigent Router` using `fleet/paperclip-omnigent-router.md` as its durable instruction body. Point the agent at the Omnigent agent definition in `fleet/fleet-dispatcher.yaml`. Keep budget caps and wake-on-demand enabled; do not create a second execution owner for a routed issue.

## Verification

- Seven focused unit tests pass.
- Version parsing, baseline migration, capability-contract alignment, compatibility refusal, and governed Devin/Cursor policy selection are covered by focused tests.
- A normal `queue-cleanup` task selected `paperclip-native` and produced Vault plus outbox evidence.
- A `multi-model` task selected the `poly` Ringer-over-Omnigent profile, generated a valid two-worker Ringer dry-run manifest and receipt, and produced Vault plus outbox evidence.
- The smoke authority reference was `JAC-ROUTER-SMOKE`.

## Commands

```bash
uv run python scripts/fleet_dispatch.py "Reconcile queue item" --route --tag queue-cleanup --bead-id JAC-ROUTER-SMOKE
OMNIGENT_FLEET_ENGINES=mock uv run python scripts/fleet_dispatch.py "Compare approaches" --route --tag multi-model --dry-run --bead-id JAC-ROUTER-SMOKE
uv run --extra dev pytest fleet/tests/test_fleet_dispatch.py -q
```
