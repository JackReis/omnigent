"""Bounded Omnigent-to-Ringer dispatch integration for the local fleet."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "runtime"
DEFAULT_ALLOWED_ROOT = Path("/Users/hermes/Vault/coordination")
DEFAULT_ENGINES = ("kimi", "mock")
DEFAULT_DISPATCH = {
    "agent": "hermes",
    "provider_preference": "ollama-cloud",
    "model": "kimi-k3",
    "engine": "kimi",
    "required_when_unspecified": True,
    "allow_per_task_override": True,
    "optional_routes": ("ringer", "devin", "cursor"),
    "route_when_available": True,
}
HEAVY_DISPATCH = {
    "model": "deepseek-v4-flash",
    "tags": frozenset({"high-capability", "heavy", "complex", "deepseek"}),
}
MAX_FANOUT = 4
ROUTE_NATIVE = "paperclip-native"
ROUTE_DIRECT = "omnigent-direct"
ROUTE_RINGER = "ringer-omnigent"

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "poly": {"orchestrator": "poly", "harness": "hermes", "engines": "kimi,mock", "fanout": 2},
    "planner": {"orchestrator": "single", "harness": "claude-native", "engines": "kimi", "fanout": 1},
    "coder": {"orchestrator": "single", "harness": "codex-native", "engines": "kimi", "fanout": 1},
    "review": {"orchestrator": "panel", "harness": "hermes", "engines": "kimi,mock", "fanout": 2},
}
CORE_SERVICES = ("holographic", "honcho", "hindsight", "openbrain1", "gbrain", "vaults")
LANE_REGISTRY_PATH = PROJECT_ROOT / "fleet" / "lane-registry.yaml"
BASELINE_VERSION = "1.0.0"
SUPPORTED_VERSIONS = {
    "lane_contract_version": BASELINE_VERSION,
    "adapter_version": BASELINE_VERSION,
    "policy_version": BASELINE_VERSION,
}
VERSION_FIELDS = tuple(SUPPORTED_VERSIONS)
RESERVED_PAPERCLIP_RUNTIME_VARIABLES = frozenset({"PAPERCLIP_RUN_SCRATCH_DIR"})
DEFAULT_LANE_GOVERNANCE = {
    "owner": "ringer",
    "allowed_scope": "execute_assigned_task",
    "return_control_to": "ringer",
    "return_control_on": ["failure", "ambiguity", "out_of_scope"],
}
GOVERNANCE_POLICY = {
    "authority": "paperclip",
    "execution_spine": "ringer",
    "lifecycle_owner": "ringer",
    "registered_lane_scope": "execution_only",
    "omnigent_direct_bypass": "denied_for_registered_lanes",
    "retry": {"max_additional_attempts": 1, "on_exhaustion": "blocked"},
    "escalation": "paperclip_issue_owner_or_board",
}


def validate_adapter_config(config: Mapping[str, Any]) -> None:
    """Reject Paperclip-owned runtime variables from adapter configuration."""
    if not isinstance(config, Mapping):
        raise ValueError("adapter config must be an object")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                if key_text in RESERVED_PAPERCLIP_RUNTIME_VARIABLES:
                    raise ValueError(
                        f"env.{key_text} is a reserved Paperclip runtime variable "
                        "and cannot be set from adapter config"
                    )
                walk(child, f"{path}.{key_text}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(config, "adapter")


def _parse_version(value: Any, field: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"{field} must use semantic versioning (for example {BASELINE_VERSION})")
    return tuple(int(part) for part in value.split("."))


def _normalize_lane(lane_name: str, lane: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(lane)
    for field in VERSION_FIELDS:
        value = normalized.setdefault(field, BASELINE_VERSION)
        _parse_version(value, f"{lane_name}.{field}")
    capabilities = list(normalized.get("capabilities", []))
    mapping = normalized.get("capability_mapping") or {}
    if not isinstance(mapping, dict):
        raise ValueError(f"{lane_name}.capability_mapping must be an object")
    mapping = dict(mapping)
    mapping.setdefault("contract_version", normalized["lane_contract_version"])
    mapping.setdefault("capabilities", capabilities)
    if mapping["contract_version"] != normalized["lane_contract_version"]:
        raise ValueError(
            f"{lane_name}.capability_mapping.contract_version must match lane_contract_version"
        )
    _parse_version(mapping["contract_version"], f"{lane_name}.capability_mapping.contract_version")
    normalized["capability_mapping"] = mapping
    lane_governance = normalized.get("governance") or {}
    if not isinstance(lane_governance, dict):
        raise ValueError(f"{lane_name}.governance must be an object")
    lane_governance = {**DEFAULT_LANE_GOVERNANCE, **lane_governance}
    normalized["governance"] = lane_governance
    paths = normalized.get("paths")
    if paths is not None:
        if not isinstance(paths, dict) or not {"executable", "config", "state"}.issubset(paths):
            raise ValueError(f"{lane_name}.paths must include executable, config, and state")
        executable = paths["executable"]
        if not isinstance(executable, str) or not executable or executable.startswith("/"):
            raise ValueError(f"{lane_name}.paths.executable must be a portable command name")
        for field in ("config", "state"):
            value = paths[field]
            if not isinstance(value, str) or not (
                value == "~" or value.startswith("~/") or value.startswith("${HOME}/")
            ):
                raise ValueError(f"{lane_name}.paths.{field} must be home-relative")
    invocation = normalized.get("invocation")
    if invocation is not None and (
        not isinstance(invocation, dict)
        or not isinstance(invocation.get("args"), list)
        or not all(isinstance(arg, str) for arg in invocation["args"])
    ):
        raise ValueError(f"{lane_name}.invocation.args must be a list of strings")
    return normalized


def check_lane_compatibility(lane: dict[str, Any]) -> dict[str, Any]:
    """Report whether a lane can run under this router's version contracts."""
    versions = {field: lane[field] for field in VERSION_FIELDS}
    incompatible = []
    for field, supported in SUPPORTED_VERSIONS.items():
        if _parse_version(versions[field], field)[0] != _parse_version(supported, field)[0]:
            incompatible.append(f"{field}={versions[field]} (supported major {_parse_version(supported, field)[0]})")
    return {
        "compatible": not incompatible,
        "versions": versions,
        "reason": "compatible" if not incompatible else "; ".join(incompatible),
    }


def _ensure_requested_versions(
    lane_name: str,
    lane: dict[str, Any],
    requested_versions: dict[str, str] | None,
) -> None:
    if not requested_versions:
        return
    for field, requested in requested_versions.items():
        if field not in VERSION_FIELDS:
            raise ValueError(f"unsupported lane version field: {field}")
        requested_major = _parse_version(requested, field)[0]
        actual = lane[field]
        actual_major = _parse_version(actual, f"{lane_name}.{field}")[0]
        if requested_major != actual_major:
            raise ValueError(
                f"lane {lane_name} is incompatible for {field}: "
                f"requested {requested}, registered {actual}"
            )


def serialize_lane_registry(registry: dict[str, dict[str, Any]]) -> str:
    """Serialize normalized lane contracts without dropping version metadata."""
    payload = {
        "version": 1,
        "description": "Shared execution-lane registry for Paperclip authority and Ringer execution.",
        "governance": GOVERNANCE_POLICY,
        "lanes": {name: _normalize_lane(name, lane) for name, lane in registry.items()},
    }
    return yaml.safe_dump(payload, sort_keys=False)


def load_lane_registry() -> dict[str, dict[str, Any]]:
    """Load and validate the shared Paperclip/Ringer lane contract."""
    raw = yaml.safe_load(LANE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    adapter_config = raw.get("adapter_config")
    if adapter_config is not None:
        validate_adapter_config(adapter_config)
    lanes = raw.get("lanes")
    if not isinstance(lanes, dict) or not lanes:
        raise ValueError(f"lane registry is empty or invalid: {LANE_REGISTRY_PATH}")
    normalized_lanes: dict[str, dict[str, Any]] = {}
    for lane_name, lane in lanes.items():
        if not isinstance(lane, dict):
            raise ValueError(f"lane registry entry is invalid: {lane_name}")
        if not {"paperclip", "ringer"}.issubset(set(lane.get("registrations", []))):
            raise ValueError(f"lane is not registered with Paperclip and Ringer: {lane_name}")
        normalized = _normalize_lane(lane_name, lane)
        compatibility = check_lane_compatibility(normalized)
        if not compatibility["compatible"]:
            raise ValueError(f"lane {lane_name} is incompatible: {compatibility['reason']}")
        normalized_lanes[lane_name] = normalized
    return normalized_lanes


def _requested_lane(normalized: set[str]) -> tuple[str, dict[str, Any]] | None:
    lanes = load_lane_registry()
    aliases = {
        "cursor-native": "cursor",
        "curser": "cursor",
        "devin-native": "devin",
        "devon": "devin",
    }
    for item in normalized:
        lane_name = aliases.get(item, item)
        if lane_name in lanes:
            return lane_name, lanes[lane_name]
    capability_preferences = (
        ("editor", "cursor"),
        ("refactor", "cursor"),
        ("lint", "cursor"),
        ("linting", "cursor"),
        ("environment_setup", "devin"),
        ("cross_service_coordination", "devin"),
        ("orchestration", "devin"),
    )
    for capability, lane_name in capability_preferences:
        if capability in normalized:
            return lane_name, lanes[lane_name]
    return None


def publish_fleet_event(event: str, handoff: dict[str, Any]) -> dict[str, Any]:
    """Persist an idempotent event to the Vault mirror and retryable service outbox."""
    runtime_root = Path(os.environ.get("OMNIGENT_FLEET_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser().resolve()
    durable_ref = handoff["authority"].get("bead_id") or handoff["authority"].get("paperclip_issue") or _safe_slug(handoff["input"]["prompt"])
    identity = json.dumps({"event": event, "ref": durable_ref, "decision": handoff["decision"]}, sort_keys=True)
    event_id = hashlib.sha256(identity.encode()).hexdigest()[:20]
    payload = {
        "schema": "fleet-service-update/v1",
        "event_id": event_id,
        "event": event,
        "durable_ref": durable_ref,
        "occurred_at": datetime.now(UTC).isoformat(),
        "route": handoff["decision"],
        "evidence": handoff["evidence"],
        "deliveries": {service: {"status": "queued", "attempts": 0} for service in CORE_SERVICES},
        "retry": {"policy": "exponential", "base_seconds": 30, "max_seconds": 3600, "never_drop": True},
    }
    outbox_dir = runtime_root / "outbox"
    vault_dir = runtime_root / "vault" / "fleet-events"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)
    outbox_path = outbox_dir / f"{event_id}.json"
    vault_path = vault_dir / f"{event_id}.md"
    if not outbox_path.exists():
        outbox_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not vault_path.exists():
        vault_path.write_text(
            f"# Fleet Event {event_id}\n\n- Event: {event}\n- Reference: {durable_ref}\n"
            f"- Route: {handoff['decision']['route']}\n- Receipt: {handoff['evidence'].get('receipt')}\n",
            encoding="utf-8",
        )
    return {"event_id": event_id, "outbox_path": str(outbox_path), "vault_path": str(vault_path)}


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "dispatch"


def _allowed_engines() -> tuple[str, ...]:
    configured = os.environ.get("OMNIGENT_FLEET_ENGINES", "")
    if not configured.strip():
        return DEFAULT_ENGINES
    return tuple(item.strip() for item in configured.split(",") if item.strip())


def _resolve_workspace(workspace: str | None, run_name: str) -> Path:
    allowed_root = Path(
        os.environ.get("OMNIGENT_FLEET_ALLOWED_ROOT", str(DEFAULT_ALLOWED_ROOT))
    ).expanduser().resolve()
    if workspace:
        resolved = Path(workspace).expanduser().resolve()
        if resolved != allowed_root and allowed_root not in resolved.parents:
            raise ValueError(f"workspace must be inside {allowed_root}")
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    runtime_root = Path(
        os.environ.get("OMNIGENT_FLEET_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))
    ).expanduser().resolve()
    resolved = runtime_root / "work" / run_name
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _ringer_binary() -> str:
    configured = os.environ.get("OMNIGENT_RINGER_BIN")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"OMNIGENT_RINGER_BIN is not executable: {path}")
        return str(path)
    discovered = shutil.which("ringer")
    if not discovered:
        fallback = Path.home() / ".local" / "bin" / "ringer"
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return str(fallback)
        raise RuntimeError("ringer is not on PATH; set OMNIGENT_RINGER_BIN")
    return discovered


def select_route(
    *,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
    policy_flags: list[str] | None = None,
    agent_class: str = "general",
    requested_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Select a deterministic execution path from durable task metadata."""
    normalized = {
        item.strip().lower()
        for item in [*(tags or []), *(capabilities or []), *(policy_flags or [])]
        if item.strip()
    }
    requested_lane = _requested_lane(normalized)
    if requested_lane:
        lane_name, lane = requested_lane
        _ensure_requested_versions(lane_name, lane, requested_versions)
        compatibility = check_lane_compatibility(lane)
        return {
            "route": ROUTE_RINGER,
            "profile": lane.get("default_profile", "coder"),
            "lane": lane_name,
            "versions": compatibility["versions"],
            "capability_mapping": lane["capability_mapping"],
            "reason": "registered lane requires Paperclip and Ringer governance",
        }
    if "paperclip-native" in normalized or "local-workflow" in normalized:
        return {"route": ROUTE_NATIVE, "profile": None, "reason": "explicit native policy"}
    if "omnigent-direct" in normalized or "single-harness" in normalized:
        profile = agent_class if agent_class in PROFILE_DEFAULTS else "planner"
        return {"route": ROUTE_DIRECT, "profile": profile, "reason": "direct harness requested"}
    if normalized & HEAVY_DISPATCH["tags"]:
        profile = agent_class if agent_class in PROFILE_DEFAULTS else "planner"
        return {"route": ROUTE_RINGER, "profile": profile, "reason": "heavy worker requested"}
    if normalized & {"meta-harness", "multi-model", "multi-agent", "ringer", "poly"}:
        profile = "poly" if normalized & {"poly", "multi-agent", "multi-model"} else (
            agent_class if agent_class in PROFILE_DEFAULTS else "review"
        )
        return {"route": ROUTE_RINGER, "profile": profile, "reason": "meta-harness coordination requested"}
    return {"route": ROUTE_NATIVE, "profile": None, "reason": "normal workflow task"}


def _dispatch_model(normalized: set[str]) -> str:
    if normalized & HEAVY_DISPATCH["tags"]:
        return HEAVY_DISPATCH["model"]
    return DEFAULT_DISPATCH["model"]


def route_task(
    prompt: str,
    *,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
    policy_flags: list[str] | None = None,
    agent_class: str = "general",
    paperclip_issue: str | None = None,
    bead_id: str | None = None,
    workspace: str | None = None,
    dry_run: bool = False,
    model: str | None = None,
    lane_contract_version: str | None = None,
    adapter_version: str | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    """Create one unified handoff receipt and execute when the route is supported."""
    decision = select_route(
        tags=tags,
        capabilities=capabilities,
        policy_flags=policy_flags,
        agent_class=agent_class,
        requested_versions={
            field: value
            for field, value in {
                "lane_contract_version": lane_contract_version,
                "adapter_version": adapter_version,
                "policy_version": policy_version,
            }.items()
            if value is not None
        },
    )
    handoff = {
        "schema": "fleet-handoff/v1",
        "input": {
            "prompt": prompt,
            "tags": tags or [],
            "capabilities": capabilities or [],
            "policy_flags": policy_flags or [],
        },
        "authority": {"paperclip_issue": paperclip_issue, "bead_id": bead_id},
        "decision": decision,
        "expected_output": {"report": "report.md", "status": "PASS|BLOCKED|FAIL"},
        "evidence": {"manifest": None, "receipt": None, "artifacts": []},
        "fallback": ROUTE_NATIVE,
    }
    if decision["route"] == ROUTE_NATIVE:
        evidence = publish_fleet_event("policy_decision", handoff)
        return {"ok": True, "executed": False, "handoff": handoff, "fleet_event": evidence}
    profile = PROFILE_DEFAULTS[decision["profile"]]
    normalized = {
        item.strip().lower()
        for item in [*(tags or []), *(capabilities or []), *(policy_flags or [])]
        if item.strip()
    }
    selected_model = model or _dispatch_model(normalized)
    if decision["route"] == ROUTE_DIRECT:
        handoff["decision"]["harness"] = profile["harness"]
        handoff["decision"]["orchestrator"] = profile["orchestrator"]
        evidence = publish_fleet_event("dispatch", handoff)
        return {"ok": True, "executed": False, "handoff": handoff, "fleet_event": evidence}
    try:
        profile_engines = [engine for engine in profile["engines"].split(",") if engine in _allowed_engines()]
        if not profile_engines:
            raise RuntimeError("no profile engines are currently allowed")
        result = dispatch_prompt(
            prompt,
            title=f"paperclip-{decision['profile']}",
            engines=",".join(profile_engines),
            fanout=profile["fanout"],
            workspace=workspace,
            paperclip_issue=paperclip_issue,
            bead_id=bead_id,
            dry_run=dry_run,
            profile=decision["profile"],
            lane=decision.get("lane"),
            model=selected_model,
        )
    except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        handoff["decision"] = {"route": ROUTE_NATIVE, "profile": None, "reason": f"fallback: {exc}"}
        evidence = publish_fleet_event("failure", handoff)
        return {"ok": True, "executed": False, "handoff": handoff, "fleet_event": evidence}
    handoff["evidence"].update({"manifest": result["manifest_path"], "receipt": result["receipt_path"]})
    evidence = publish_fleet_event("completion" if result["ok"] else "failure", handoff)
    return {"ok": result["ok"], "executed": True, "handoff": handoff, "dispatch": result, "fleet_event": evidence}


def build_manifest(
    prompt: str,
    *,
    title: str = "omnigent-dispatch",
    engines: str = "kimi",
    fanout: int = 1,
    workspace: str | None = None,
    paperclip_issue: str | None = None,
    bead_id: str | None = None,
    profile: str = "planner",
    lane: str | None = None,
    model: str = DEFAULT_DISPATCH["model"],
) -> tuple[dict[str, Any], Path]:
    """Build a bounded Ringer manifest without executing it."""
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("prompt must not be empty")
    if fanout < 1 or fanout > MAX_FANOUT:
        raise ValueError(f"fanout must be between 1 and {MAX_FANOUT}")
    if lane is not None and lane not in load_lane_registry():
        raise ValueError(f"lane is not registered: {lane}")

    requested_engines = tuple(item.strip() for item in engines.split(",") if item.strip())
    if not requested_engines:
        raise ValueError("at least one engine is required")
    allowed = _allowed_engines()
    disallowed = sorted(set(requested_engines) - set(allowed))
    if disallowed:
        raise ValueError(f"engines not allowed: {', '.join(disallowed)}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"omnigent-{_safe_slug(title)}-{timestamp}"
    workdir = _resolve_workspace(workspace, run_name)
    report_name = "report.md"
    tasks = []
    for index in range(fanout):
        engine = requested_engines[index % len(requested_engines)]
        task_key = f"dispatch-{index + 1}-{_safe_slug(engine)}"
        role_suffix = ""
        if fanout > 1:
            role_suffix = (
                f"\n\nYou are fleet worker {index + 1} of {fanout}. Produce an independent "
                "result and do not coordinate through untracked channels."
            )
        if engine == "mock":
            report = {
                "status": "PASS",
                "source": "omnigent",
                "route": "ringer",
                "worker": index + 1,
                "prompt": clean_prompt,
            }
            spec = (
                f"MOCK_FILE: {report_name}\n"
                f"{json.dumps(report, indent=2)}\n"
                "MOCK_END"
            )
        else:
            spec = (
                f"{clean_prompt}{role_suffix}\n\n"
                f"Write a concise completion report to {report_name} in the current task directory."
            )
        task = {
                "key": task_key,
                "engine": engine,
                "agent": DEFAULT_DISPATCH["agent"],
                "provider_preference": DEFAULT_DISPATCH["provider_preference"],
                "task_type": "omnigent-fleet-dispatch",
                "spec": spec,
                "check": (
                    "python3 -c 'from pathlib import Path; "
                    f"p=Path(\"{report_name}\"); "
                    "raise SystemExit(0 if p.is_file() and p.stat().st_size else 1)'"
                ),
                "expect_files": [report_name],
                "timeout_s": 1800,
                "full_access": False,
                "verified": "Worker produced a non-empty tracked completion report.",
                "governance": {
                    "authority": "paperclip",
                    "execution_spine": "ringer",
                    "lifecycle_owner": "ringer",
                    "direct_omnigent_bypass": False,
                    "max_additional_attempts": 1,
                    "escalation": "paperclip_issue_owner_or_board",
                },
            }
        if engine != "mock":
            task["model"] = model
        if lane:
            lane_contract = load_lane_registry()[lane]
            compatibility = check_lane_compatibility(lane_contract)
            task["lane"] = lane
            task["lane_contract_version"] = compatibility["versions"]["lane_contract_version"]
            task["adapter_version"] = compatibility["versions"]["adapter_version"]
            task["policy_version"] = compatibility["versions"]["policy_version"]
            task["capability_mapping"] = lane_contract["capability_mapping"]
            task["lane_governance"] = lane_contract["governance"]
            if "paths" in lane_contract:
                task["paths"] = lane_contract["paths"]
            if "invocation" in lane_contract:
                task["invocation"] = lane_contract["invocation"]
        if paperclip_issue:
            task["paperclip_issue"] = paperclip_issue.strip()
        if bead_id:
            task["bead_id"] = bead_id.strip()
        tasks.append(task)

    profile_config = PROFILE_DEFAULTS.get(profile, PROFILE_DEFAULTS["planner"])
    manifest = {
        "run_name": run_name,
        "workdir": str(workdir),
        "risk": "medium",
        "orchestrator": {
            "provider": "local",
            "model": model,
            "agent": DEFAULT_DISPATCH["agent"],
            "provider_preference": DEFAULT_DISPATCH["provider_preference"],
            "optional_routes": list(DEFAULT_DISPATCH["optional_routes"]),
            "route_when_available": DEFAULT_DISPATCH["route_when_available"],
            "family": "meta-harness",
            "runtime": "omnigent-ringer",
            "profile": profile,
            "harness": profile_config["harness"],
            "orchestrator": profile_config["orchestrator"],
            "attestation": "Bounded local dispatch through the existing Ringer execution spine",
        },
        "max_parallel": min(fanout, 2),
        "worktrees": False,
        "tasks": tasks,
    }
    return manifest, workdir


def dispatch_prompt(
    prompt: str,
    title: str = "omnigent-dispatch",
    engines: str = "kimi",
    fanout: int = 1,
    workspace: str | None = None,
    paperclip_issue: str | None = None,
    bead_id: str | None = None,
    dry_run: bool = False,
    profile: str = "planner",
    lane: str | None = None,
    model: str = DEFAULT_DISPATCH["model"],
) -> dict[str, Any]:
    """Route a prompt through Ringer and return its immutable receipt metadata."""
    manifest, workdir = build_manifest(
        prompt,
        title=title,
        engines=engines,
        fanout=fanout,
        workspace=workspace,
        paperclip_issue=paperclip_issue,
        bead_id=bead_id,
        profile=profile,
        lane=lane,
        model=model,
    )
    runtime_root = Path(
        os.environ.get("OMNIGENT_FLEET_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT))
    ).expanduser().resolve()
    manifest_dir = runtime_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{manifest['run_name']}.ringer.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    command = [
        _ringer_binary(),
        "run",
        str(manifest_path),
        "--identity",
        "omnigent",
        "--no-dashboard",
    ]
    if dry_run:
        command.append("--dry-run")
    env = os.environ.copy()
    env.setdefault("RINGER_NO_CATALOG_REFRESH", "1")
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120 if dry_run else 7200,
        check=False,
    )
    response = {
        "ok": result.returncode == 0,
        "dry_run": dry_run,
        "run_name": manifest["run_name"],
        "manifest_path": str(manifest_path),
        "workdir": str(workdir),
        "engines": [task["engine"] for task in manifest["tasks"]],
        "returncode": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-4000:],
    }
    receipt_dir = runtime_root / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{manifest['run_name']}.json"
    response["receipt_path"] = str(receipt_path)
    receipt_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    return response
