#!/bin/sh
set -eu

export PATH="$HOME/.local/bin:$HOME/homebrew/bin:$PATH"
exec omnigent server stop
