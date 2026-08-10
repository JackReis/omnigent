from pathlib import Path

import pytest

from omnigent.fleet_dispatch import (
    build_manifest,
    check_lane_compatibility,
    load_lane_registry,
    publish_fleet_event,
    route_task,
    select_route,
    serialize_lane_registry,
    validate_adapter_config,
)


def test_build_manifest_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path))
    manifest, workspace = build_manifest(
        "Check the route",
        engines="mock",
        fanout=2,
        workspace=str(tmp_path / "work"),
        paperclip_issue="JAC-TEST",
        bead_id="fleet-test",
    )

    assert workspace == tmp_path / "work"
    assert manifest["max_parallel"] == 2
    assert len(manifest["tasks"]) == 2
    assert all(task["engine"] == "mock" for task in manifest["tasks"])
    assert all(task["full_access"] is False for task in manifest["tasks"])
    assert all(task["paperclip_issue"] == "JAC-TEST" for task in manifest["tasks"])
    assert all(task["bead_id"] == "fleet-test" for task in manifest["tasks"])


def test_build_manifest_records_default_ollamacloud_kimi_k3_preference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path))
    manifest, _ = build_manifest(
        "Use the default dispatch route",
        engines="mock",
        workspace=str(tmp_path / "work"),
    )
    task = manifest["tasks"][0]
    assert task["agent"] == "hermes"
    assert task["provider_preference"] == "ollama-cloud"
    assert "model" not in task
    assert manifest["orchestrator"]["model"] == "kimi-k3"
    assert manifest["orchestrator"]["optional_routes"] == ["ringer", "devin", "cursor"]


def test_route_task_selects_deepseek_for_heavy_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "omnigent.fleet_dispatch.dispatch_prompt",
        lambda *args, **kwargs: {
            "ok": True,
            "manifest_path": "manifest.json",
            "receipt_path": "receipt.json",
            "model": kwargs["model"],
        },
    )
    result = route_task(
        "Handle the high-capability investigation",
        tags=["high-capability"],
        dry_run=True,
    )
    assert result["dispatch"]["model"] == "deepseek-v4-flash"


def test_build_manifest_rejects_external_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path / "allowed"))

    with pytest.raises(ValueError, match="workspace must be inside"):
        build_manifest("Check the route", engines="mock", workspace=str(tmp_path / "other"))


def test_build_manifest_rejects_unapproved_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ENGINES", "kimi,mock")

    with pytest.raises(ValueError, match="engines not allowed"):
        build_manifest("Check the route", engines="codex")


def test_adapter_config_rejects_reserved_paperclip_runtime_variable() -> None:
    with pytest.raises(ValueError, match=r"PAPERCLIP_RUN_SCRATCH_DIR.*reserved Paperclip"):
        validate_adapter_config({"env": {"PAPERCLIP_RUN_SCRATCH_DIR": "/tmp"}})


def test_adapter_config_allows_non_reserved_environment() -> None:
    validate_adapter_config({"env": {"RINGER_WORKSPACE": "/tmp/work"}})


def test_select_route_keeps_normal_work_in_paperclip() -> None:
    assert select_route(tags=["queue-cleanup"])["route"] == "paperclip-native"


def test_select_route_uses_poly_for_multi_model() -> None:
    decision = select_route(tags=["multi-model"], agent_class="review")
    assert decision == {
        "route": "ringer-omnigent",
        "profile": "poly",
        "reason": "meta-harness coordination requested",
    }


def test_registered_cursor_lane_cannot_bypass_governance() -> None:
    decision = select_route(tags=["cursor-native", "single-harness"])
    assert decision == {
        "route": "ringer-omnigent",
        "profile": "coder",
        "lane": "cursor",
        "versions": {
            "lane_contract_version": "1.0.0",
            "adapter_version": "1.0.0",
            "policy_version": "1.0.0",
        },
        "capability_mapping": {
            "contract_version": "1.0.0",
            "capabilities": ["editor", "refactor", "coding", "testing", "linting"],
        },
        "reason": "registered lane requires Paperclip and Ringer governance",
    }


def test_editor_capability_selects_cursor_lane() -> None:
    decision = select_route(capabilities=["editor", "refactor"])
    assert decision["route"] == "ringer-omnigent"
    assert decision["lane"] == "cursor"


@pytest.mark.parametrize(
    ("spoken_name", "expected_lane"),
    [("curser", "cursor"), ("devon", "devin")],
)
def test_common_spoken_lane_aliases_select_registered_workflows(
    spoken_name: str, expected_lane: str
) -> None:
    decision = select_route(tags=[spoken_name])
    assert decision["route"] == "ringer-omnigent"
    assert decision["lane"] == expected_lane


def test_orchestration_capability_selects_devin_lane() -> None:
    decision = select_route(capabilities=["cross_service_coordination"])
    assert decision["route"] == "ringer-omnigent"
    assert decision["lane"] == "devin"


def test_registered_devin_lane_uses_paperclip_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "omnigent.fleet_dispatch.dispatch_prompt",
        lambda *_args, **_kwargs: {
            "ok": True,
            "manifest_path": "manifest.json",
            "receipt_path": "receipt.json",
        },
    )
    result = route_task("Coordinate a deployment", capabilities=["devin"])
    assert result["handoff"]["decision"]["route"] == "ringer-omnigent"
    assert result["handoff"]["decision"]["lane"] == "devin"
    assert result["handoff"]["authority"] == {"paperclip_issue": None, "bead_id": None}


def test_lane_registry_registers_all_lanes_with_both_governance_surfaces() -> None:
    registry = load_lane_registry()
    assert {"devin", "cursor"}.issubset(registry)
    assert all(
        {"paperclip", "ringer"}.issubset(lane["registrations"])
        for lane in registry.values()
    )
    assert all(
        {"lane_contract_version", "adapter_version", "policy_version"} <= set(lane)
        for lane in registry.values()
    )
    assert all(
        lane["capability_mapping"]["contract_version"] == lane["lane_contract_version"]
        for lane in registry.values()
    )


def test_registered_lanes_cannot_bypass_ringer_governance() -> None:
    registry = load_lane_registry()

    assert all(lane["omnigent_direct_allowed"] is False for lane in registry.values())


def test_lane_registry_declares_ringer_ownership_and_handback() -> None:
    registry = load_lane_registry()
    expected = {
        "owner": "ringer",
        "allowed_scope": "execute_assigned_task",
        "return_control_to": "ringer",
        "return_control_on": ["failure", "ambiguity", "out_of_scope"],
    }
    assert all(lane["governance"] == expected for lane in registry.values())


def test_devin_and_cursor_registry_paths_are_current() -> None:
    registry = load_lane_registry()
    assert registry["devin"]["paths"] == {
        "executable": "devin",
        "config": "~/.config/devin/config.json",
        "state": "~/.config/devin",
    }
    assert registry["cursor"]["paths"] == {
        "executable": "cursor-agent",
        "config": "~/.cursor",
        "state": "~/.cursor/projects",
    }


def test_lane_manifest_carries_adapter_paths_and_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path))
    manifest, _ = build_manifest(
        "Coordinate the editor workflow",
        engines="mock",
        workspace=str(tmp_path / "work"),
        lane="cursor",
    )
    task = manifest["tasks"][0]
    assert task["paths"]["executable"] == "cursor-agent"
    assert task["invocation"]["args"] == ["--print", "--output-format", "json", "--trust"]

    manifest, _ = build_manifest(
        "Coordinate the cloud workflow",
        engines="mock",
        workspace=str(tmp_path / "work-devin"),
        lane="devin",
    )
    task = manifest["tasks"][0]
    assert task["paths"]["executable"] == "devin"
    assert task["invocation"]["args"] == [
        "--print",
        "--permission-mode",
        "dangerous",
        "--respect-workspace-trust",
        "false",
        "--",
    ]


def test_lane_registry_rejects_machine_specific_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "lane-registry.yaml"
    registry_path.write_text(
        "lanes:\n"
        "  local:\n"
        "    registrations: [paperclip, ringer]\n"
        "    paths:\n"
        "      executable: /Users/example/bin/agent\n"
        "      config: /Users/example/.config/agent/config.json\n"
        "      state: ~/.agent\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("omnigent.fleet_dispatch.LANE_REGISTRY_PATH", registry_path)
    with pytest.raises(ValueError, match="portable command name"):
        load_lane_registry()


def test_legacy_lane_defaults_to_baseline_and_serializes_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "lane-registry.yaml"
    registry_path.write_text(
        "lanes:\n"
        "  legacy:\n"
        "    registrations: [paperclip, ringer]\n"
        "    capabilities: [general]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("omnigent.fleet_dispatch.LANE_REGISTRY_PATH", registry_path)
    registry = load_lane_registry()
    lane = registry["legacy"]
    assert lane["lane_contract_version"] == "1.0.0"
    assert lane["adapter_version"] == "1.0.0"
    assert lane["policy_version"] == "1.0.0"
    assert lane["governance"]["owner"] == "ringer"
    assert "lane_contract_version: 1.0.0" in serialize_lane_registry(registry)
    assert "lifecycle_owner: ringer" in serialize_lane_registry(registry)


def test_incompatible_lane_is_reported_clearly() -> None:
    lane = {
        "lane_contract_version": "2.0.0",
        "adapter_version": "1.0.0",
        "policy_version": "1.0.0",
    }
    result = check_lane_compatibility(lane)
    assert result["compatible"] is False
    assert "lane_contract_version=2.0.0" in result["reason"]


def test_requested_version_mismatch_refuses_governed_route() -> None:
    with pytest.raises(ValueError, match="incompatible for adapter_version"):
        select_route(
            capabilities=["editor"],
            requested_versions={"adapter_version": "2.0.0"},
        )


def test_lane_manifest_carries_governance_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_ALLOWED_ROOT", str(tmp_path))
    manifest, _ = build_manifest(
        "Refactor the editor integration",
        engines="mock",
        workspace=str(tmp_path / "work"),
        lane="cursor",
    )
    task = manifest["tasks"][0]
    assert task["lane"] == "cursor"
    assert task["governance"] == {
        "authority": "paperclip",
        "execution_spine": "ringer",
        "lifecycle_owner": "ringer",
        "direct_omnigent_bypass": False,
        "max_additional_attempts": 1,
        "escalation": "paperclip_issue_owner_or_board",
    }
    assert task["lane_governance"]["return_control_to"] == "ringer"
    assert task["lane_contract_version"] == "1.0.0"
    assert task["adapter_version"] == "1.0.0"
    assert task["policy_version"] == "1.0.0"
    assert task["capability_mapping"]["contract_version"] == "1.0.0"


def test_route_task_describes_direct_harness() -> None:
    result = route_task("Plan it", tags=["single-harness"], agent_class="planner")
    assert result["executed"] is False
    assert result["handoff"]["decision"]["route"] == "omnigent-direct"
    assert result["handoff"]["decision"]["harness"] == "claude-native"


def test_publish_fleet_event_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_FLEET_RUNTIME_ROOT", str(tmp_path))
    handoff = route_task("Queue cleanup", tags=["queue-cleanup"], bead_id="JAC-TEST")["handoff"]
    first = publish_fleet_event("policy_decision", handoff)
    second = publish_fleet_event("policy_decision", handoff)
    assert first == second
    assert Path(first["outbox_path"]).is_file()
    assert Path(first["vault_path"]).is_file()
