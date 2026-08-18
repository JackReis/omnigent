# Ringer Workflow Path Alignment

Date: 2026-08-02

The governed lane registry now records portable entrypoints and home-relative
config/state locations for the Devin and Cursor workflows:

- Devin executable: `devin`
- Devin config/state: `~/.config/devin/config.json`, `~/.config/devin`
- Cursor executable: `cursor-agent`
- Cursor config/state: `~/.cursor`, `~/.cursor/projects`

Versioned install targets are intentionally not stored; each host resolves the
command through its own `PATH`, avoiding stale machine-specific symlink targets.

The manifest builder carries each lane's path and invocation metadata into
Ringer tasks without changing the existing Paperclip/Ringer governance guard.

Validation:

- `23 passed` — `fleet/tests/test_fleet_dispatch.py`
- `compileall` passed for the changed Python modules
- `git diff --check` passed
- Ruff remains non-zero because of pre-existing findings elsewhere in the
  touched legacy files; no new functional lint issue was introduced.
