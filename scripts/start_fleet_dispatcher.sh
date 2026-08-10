#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="$HOME/.local/bin:$HOME/homebrew/bin:$PATH"
export OMNIGENT_RINGER_BIN="${OMNIGENT_RINGER_BIN:-$HOME/.local/bin/ringer}"
export OMNIGENT_FLEET_ALLOWED_ROOT="${OMNIGENT_FLEET_ALLOWED_ROOT:-/Users/hermes/Vault/coordination}"
export OMNIGENT_FLEET_RUNTIME_ROOT="${OMNIGENT_FLEET_RUNTIME_ROOT:-$ROOT/runtime}"
export OMNIGENT_FLEET_ENGINES="${OMNIGENT_FLEET_ENGINES:-kimi,mock}"
export OMNIGENT_BUILTIN_AGENT_DIRS="$ROOT/fleet/fleet-dispatcher.yaml"

# Stop the managed local Omnigent UI server so the fleet server can bind 6767.
launchctl stop ai.omnigent.local-server 2>/dev/null || true
launchctl stop ai.omnigent.local-host 2>/dev/null || true
sleep 2

# Run fleet server in accounts mode, exposed via Tailscale as :6777.
export OMNIGENT_AUTH_ENABLED=1
unset OMNIGENT_LOCAL_SINGLE_USER 2>/dev/null || true

nohup omnigent server --host 127.0.0.1 --port 6767 --no-open > "$HOME/.omnigent/logs/omnigent-fleet-server.log" 2>&1 &
