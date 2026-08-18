# Omnigent Fleet Dispatch Setup

## Role

Omnigent is an additive front door. It does not replace or rewrite the existing
fleet authority model:

- Aegis remains authoritative for work state.
- Ringer remains the bounded execution and immutable receipt spine.
- Paperclip remains the shared coordination and run-tracking surface.
- The Vault remains the canonical human-readable mirror.

The Paperclip agent instruction body is `fleet/paperclip-omnigent-router.md`.
It uses the shared `fleet-handoff/v1` contract and three deterministic paths:

- `paperclip-native` for normal workflow and queue work.
- `omnigent-direct` for an explicit single harness.
- `ringer-omnigent` for meta-harness or multi-model coordination.

Ringer-over-Omnigent profiles are `poly`, `planner`, `coder`, and `review`.

Registered lanes are versioned independently with `lane_contract_version`,
`adapter_version`, and `policy_version`. Capability mappings carry the contract
version they implement. Missing fields normalize to baseline `1.0.0`; a lane
with an unsupported major version is rejected with a compatibility error rather
than silently routed.

Every policy decision, dispatch, completion, or failure emits
`fleet-service-update/v1`. The same idempotent event is written to the Vault
mirror and queued for Holographic, Honcho, Hindsight, OpenBrain1, Gbrain, and
the Vaults. Unavailable connectors remain in `runtime/outbox/` with exponential
retry metadata; evidence is never dropped.

## Installed source

- Repository: `omnigent-ai/omnigent`
- Checkout: this project directory
- Install: editable `uv tool` install pinned to the checked-out commit
- Agent: `fleet/fleet-dispatcher.yaml`
- Local runtime: `runtime/`

## Default model preference

Unspecified tasks default to the OllamaCloud-powered Hermes preference with
`agent=hermes`, `model=kimi-k3`, and `engine=kimi`. Tasks tagged or described as
`high-capability`, `heavy`, `complex`, or `deepseek` use the heavier same-provider
model `deepseek-v4-flash`. Explicit per-task route, agent, provider, model, and
engine selections remain authoritative. Ringer remains the governed fan-out
option; Devin is eligible for orchestration and cross-service coordination; and
Cursor is eligible for editor-first refactors, coding, tests, and linting. These
routes are conditional: they are selected only when the lane is registered,
available, and policy-allowed.

The local Ringer config currently executes the `kimi` engine through its
authenticated Kimi Code lane. The manifests now carry the requested
OllamaCloud provider preference and model explicitly, but this checkout does not
silently claim to have switched the underlying transport.

## Start and verify

```bash
./scripts/start_fleet_dispatcher.sh
omnigent server status
python3 scripts/fleet_dispatch.py "Validate the fleet route" --engines mock --dry-run
python3 scripts/fleet_dispatch.py "Normal queue task" --route --tag queue-cleanup
python3 scripts/fleet_dispatch.py "Compare two approaches" --route --tag multi-model --dry-run
```

Start an interactive dispatch session with:

```bash
omnigent run fleet/fleet-dispatcher.yaml
```

The dispatcher path is relative to this project, not the caller's home
directory. From another working directory, use the absolute path or change to
the project root first:

```bash
cd /Users/hermes/Vault/coordination/omnigent-dispatch
python3 scripts/fleet_dispatch.py "Validate the fleet route" --engines mock --dry-run
omnigent run /Users/hermes/Vault/coordination/omnigent-dispatch/fleet/fleet-dispatcher.yaml
```

The CLI preserves automatic model selection for routed tasks. Unspecified
tasks use `kimi-k3`; `high-capability`, `heavy`, `complex`, and `deepseek` tags
select `deepseek-v4-flash`. Mock tasks intentionally omit model metadata because
the mock engine has no model argument.

## Secret handling

No secrets are stored in this project. Provider and gateway credentials must be
supplied by the existing authenticated harness or environment variables. The
dispatcher rejects engines outside `OMNIGENT_FLEET_ENGINES`.

## Rollback

```bash
./scripts/stop_fleet_dispatcher.sh
uv tool uninstall omnigent
```

This leaves Ringer, Paperclip, their configs, and their receipts untouched.
