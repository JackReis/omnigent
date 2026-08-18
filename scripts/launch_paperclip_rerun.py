from __future__ import annotations

import json
from pathlib import Path


BATCH = Path(__file__).resolve().parents[1] / "runtime" / "batch-20260801-rerun"
EXCLUSION = (
    "JAC-3662 is already handled and must be excluded from all recommendations. "
    "JAC-4344 and JAC-4390 are unresolved soak-acceptance gates and must remain held."
)


def main() -> None:
    for lane_dir in sorted(BATCH.glob("lane-*")):
        manifest_path = lane_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["run_name"] = f"{manifest['run_name'].split('-20260801-')[0]}-rerun-20260801T2035Z"
        manifest["workdir"] = str(lane_dir)
        task = manifest["tasks"][0]
        task["spec"] = task["spec"].replace(
            "Treat Paperclip as authority and preserve the four-lane guardrail.",
            "Treat Paperclip as authority and preserve the four-lane guardrail. " + EXCLUSION,
        )
        if lane_dir.name == "lane-b":
            task["spec"] = task["spec"].replace(
                "JAC-4344, ", ""
            ).replace(
                ", JAC-4390", ""
            ).replace(
                ", JAC-3662", ""
            )
        if lane_dir.name == "lane-d":
            task["spec"] += " Explicitly exclude JAC-3662, JAC-4344, and JAC-4390 from implementation recommendations."
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
