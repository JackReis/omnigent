#!/usr/bin/env python3
"""CLI wrapper for the project-local Omnigent fleet dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    uv = Path.home() / ".local" / "bin" / "uv"
    os.execv(
        str(uv),
        [
            str(uv),
            "run",
            "--python",
            "3.12",
            "python",
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omnigent.fleet_dispatch import DEFAULT_DISPATCH, dispatch_prompt, route_task


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--title", default="omnigent-dispatch")
    parser.add_argument("--engines", default="kimi")
    parser.add_argument("--fanout", type=int, default=1)
    parser.add_argument("--workspace")
    parser.add_argument("--paperclip-issue")
    parser.add_argument("--bead-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--policy-flag", action="append", default=[])
    parser.add_argument("--agent-class", default="general")
    args = parser.parse_args()
    if args.route:
        result = route_task(
            args.prompt,
            tags=args.tag,
            capabilities=args.capability,
            policy_flags=args.policy_flag,
            agent_class=args.agent_class,
            workspace=args.workspace,
            paperclip_issue=args.paperclip_issue,
            bead_id=args.bead_id,
            dry_run=args.dry_run,
            model=args.model,
        )
    else:
        result = dispatch_prompt(
        args.prompt,
        title=args.title,
        engines=args.engines,
        fanout=args.fanout,
        workspace=args.workspace,
        paperclip_issue=args.paperclip_issue,
        bead_id=args.bead_id,
        dry_run=args.dry_run,
        model=args.model or DEFAULT_DISPATCH["model"],
        )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
