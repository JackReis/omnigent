from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


RINGER_HOME = Path("/Users/hermes/.ringer")
RUNS = RINGER_HOME / "runs"
BACKUP = Path("/Users/hermes/Vault/coordination/paperclip-unblock-sweep-20260731/ringer-stale-run-backups-20260801")
PREFIX = "omnigent-paperclip-"
SUFFIX = "-rerun-20260801T2035Z"


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    BACKUP.mkdir(parents=True, exist_ok=True)
    matched = sorted(RUNS.glob(f"{PREFIX}*{SUFFIX}-*.json"))
    if len(matched) != 4:
        raise SystemExit(f"expected 4 stale runs, found {len(matched)}")

    for path in matched:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("state") != "live" or data.get("finished") is True:
            raise SystemExit(f"run is not a live stale candidate: {path}")
        shutil.copy2(path, BACKUP / path.name)
        elapsed = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(data["started_at"])).total_seconds())
        data.update(
            {
                "state": "finished",
                "finished": True,
                "finished_at": now,
                "elapsed_s": round(elapsed, 3),
                "summary": "FAIL: orphaned Ringer launcher; no worker process or active registry entry remained after launch receipt.",
                "fail": 1,
                "report_ready": False,
                "totals": {"done": 0, "fail": 1, "pass": 0, "running": 0, "tokens": 0},
            }
        )
        for task in data.get("tasks", []):
            task["status"] = "failed"
            task["verdict"] = "FAIL"
            task["error"] = "orphaned launcher: worker process absent and active-runs registry empty"
            task["check_output_tail"] = "No worker output beyond launch receipt; reconciliation stopped the stale run without retry."
            task["check_returncode"] = None
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(path.name)


if __name__ == "__main__":
    main()
