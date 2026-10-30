"""Module: plugin.yaml manifest."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_yaml_exists_and_fields():
    path = ROOT / "plugin.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["name"] == "feishu-pm-plugin"
    assert data.get("version")
    tools = data.get("provides_tools") or []
    assert "pm_health" in tools
    assert "pm_list_my_groups" in tools
    assert "pm_list_my_projects" not in tools


def test_schemas_match_manifest_tools():
    from schemas import ALL_TOOL_SCHEMAS, PM_HEALTH_SCHEMA, PM_LIST_MY_GROUPS_SCHEMA

    names = {s["name"] for s in ALL_TOOL_SCHEMAS}
    assert names == {"pm_health", "pm_list_my_groups"}
    assert PM_HEALTH_SCHEMA["description"]
    assert "feishu_user_id" in PM_LIST_MY_GROUPS_SCHEMA["parameters"]["properties"]
