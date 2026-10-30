"""Module: pm_list_my_groups tool."""

from __future__ import annotations

import json

from middleware.types import GroupBinding


def _load(raw: str) -> dict:
    return json.loads(raw)


def test_missing_identity_fails_json(configured):
    body = _load(configured.pm_list_my_groups({}))
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"

    body2 = _load(configured.pm_list_my_groups({"feishu_user_id": "  "}))
    assert body2["ok"] is False


def test_unbound_user_empty_groups_ok(configured):
    body = _load(
        configured.pm_list_my_groups({"feishu_user_id": "ou_carol"})
    )
    assert body["ok"] is True
    assert body["data"]["groups"] == []
    assert body["data"]["count"] == 0


def test_bound_user_lists_groups(configured):
    body = _load(
        configured.pm_list_my_groups({"feishu_user_id": "ou_alice"})
    )
    assert body["ok"] is True
    ids = {g["group_id"] for g in body["data"]["groups"]}
    assert ids == {"grp_ai", "grp_dev"}
    assert "project_id" not in body["data"]


def test_filters_groups_without_read_permission(configured, custom_middleware, audit):
    configured.configure(middleware=custom_middleware, audit=audit)
    body = _load(
        configured.pm_list_my_groups({"feishu_user_id": "ou_denied"})
    )
    assert body["ok"] is True
    # guest role cannot read_group_context
    assert body["data"]["groups"] == []


def test_does_not_raise_on_bad_input(configured):
    # must return str, never raise
    out = configured.pm_list_my_groups(None)  # type: ignore[arg-type]
    assert isinstance(out, str)
    assert _load(out)["ok"] is False


def test_bob_only_sees_dev(configured):
    body = _load(configured.pm_list_my_groups({"feishu_user_id": "ou_bob"}))
    ids = {g["group_id"] for g in body["data"]["groups"]}
    assert ids == {"grp_dev"}
