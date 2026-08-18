# Omnigent Router Workspace Policy Update

Date: 2026-07-31

## Result

The managed instructions for Paperclip agent `Omnigent Router` now select workspace mode after route classification and according to actual filesystem requirements.

- Non-filesystem routing, planning, research, monitoring, API, approval, and receipt tasks use `agent_default`.
- Repository reads use `shared_workspace`.
- Repository writes, concurrent writers, destructive commands, low-trust execution, branch/diff work, and isolated services use `isolated_workspace`.
- Existing workspaces are not reused automatically merely because they are attached.
- Harmless classification and routing dry runs explicitly avoid isolated workspaces.
- Every handoff receipt must include `workspace_required`, `workspace_mode`, and `workspace_reason`.

## Validation

- Paperclip returned the updated managed `AGENTS.md` successfully.
- All required workspace modes and receipt fields are present in the live instructions.
- The agent's adapter, model/provider selection, budget, heartbeat, permissions, working directory, and environment remained unchanged.
- No task, heartbeat, route, external service, repository, or Board-assigned item was executed or modified.

## Rollback

Paperclip has no config revision entry for this instructions-only update. The exact prior instructions are preserved as `AGENTS-before.md`; rollback is a PUT of that file to the managed `AGENTS.md` instructions endpoint.
