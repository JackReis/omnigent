# Poly Orchestrator Launch Report

Date: 2026-08-01

## Scope

One bounded launch canary was created for each orchestrator configured in the
Poly/Polly team: Claude Code, Codex, OpenCode, Cursor, Hermes, and Pi. Each
session received the same instruction to return only
`ORCHESTRATOR_CANARY_OK`, without file inspection, delegation, or other work.

## Results

| Configuration | Agent | Harness | Model/provider override | Outcome | Error |
|---|---|---|---|---|---|
| Claude Code | `claude-native-ui` | `claude-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |
| Codex | `codex-native-ui` | `codex-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |
| OpenCode | `opencode-native-ui` | `opencode-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |
| Cursor | `cursor-native-ui` | `cursor-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |
| Hermes | `hermes-native-ui` | `hermes-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |
| Pi | `pi-native-ui` | `pi-native` | none / native auth | Failed immediately | `runner_failed_to_start`: runner unavailable |

## Summary

- Clean launches: 0/6.
- Immediate failures: 6/6.
- Hangs/timeouts: 0/6.
- Common failure: every session reported `The runner for this session is not available — it may have failed to start. See the host logs.`
- No model override or provider-specific model was applied; all attempts used the native UI harness configuration and its existing authentication.

## Next fixes

1. Inspect Omnigent host/runner logs and verify the configured runner is online.
2. Confirm the native harness binaries and credentials for each of the six profiles.
3. Re-run one Hermes canary first, then expand to the remaining five only after a runner becomes available.

## Hermes Rerun

At 2026-08-01, a fresh Hermes canary was posted after the Omnigent API
reported two online runners. It failed immediately with the same
`runner_failed_to_start` error. The session had no assigned `runner_id` or
`host_id`; `harness` remained `hermes-native`, while `model_override` and
`llm_model` were both unset.

The runner inventory currently advertises `claude-native`, `claude-sdk`,
`codex`, `openai-agents`, `open-responses`, and `pi`, but not `hermes-native`.
The Aegis host reports Hermes-native as configured, so the remaining failure
is the runner-to-harness registration or routing path, not a missing Hermes
profile model override.

## Registration Inspection

The installed Omnigent build is `0.7.0` (built 2026-07-27). The live host and
runner processes are healthy enough to maintain WebSocket tunnel connections,
and the API reports two online runners. The failure is a capability
registration mismatch:

- `omnigent/runtime/harnesses/__init__.py:141-147` registers
  `hermes-native` and points it at `omnigent.inner.hermes_native_harness`.
- `omnigent/runner/transports/ws_tunnel/serve.py:795-802` hardcodes the
  runner hello capability list, but includes only `claude-native`,
  `claude-sdk`, `codex`, `openai-agents`, `open-responses`, and `pi`.
- Because `hermes-native` is absent from that hello frame, the server's live
  runner catalog never considers the runner eligible for Hermes sessions.
  Session creation therefore fails before a runner or host is assigned.

This is a product bug in the installed runner registration, not a provider
credential or Hermes model-selection problem. The corrective code change is
to add `hermes-native` to the runner hello capabilities, preferably by deriving
the list from the shared harness registry rather than maintaining another
hardcoded list; then restart the local host/runner and rerun the Hermes canary.

## Host Restart Check

The `ai.omnigent.local-host` launch agent was restarted on 2026-08-01. It
returned to `running` with a new process, and the host tunnel recovered. The
fresh runner catalog contained one online runner, but it still advertised only
the six hardcoded harnesses above and not `hermes-native`.

During reconnection, the new host log also recorded one transient tunnel
failure: `No module named 'omnigent.workspace_fs'`. The host reconnected and
continued, so this did not explain the persistent Hermes routing failure. The
remaining blocker is still the missing `hermes-native` capability in the
runner hello frame.

## Registration Patch

The source checkout and live Omnigent tool environment were patched to add
`hermes-native` to the runner hello capabilities. The focused WebSocket tunnel
suite passes (`33 passed`), and a direct live import now emits a `HelloFrame`
containing `hermes-native`.

The post-patch Hermes verification session still failed with
`runner_failed_to_start` because the host/API restart window left no runner
registered; this is now a separate host lifecycle/connectivity issue. The code
path that previously filtered Hermes out is fixed, but a full end-to-end canary
needs a stable host tunnel and a newly launched runner.
