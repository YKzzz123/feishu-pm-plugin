"""Module: handlers never raise; INTERNAL on unexpected errors."""

from __future__ import annotations

import json

import tools as tools_mod
from middleware.audit import ToolAudit
from middleware.errors import PluginError, error_code


def test_unexpected_exception_returns_json_not_raise(configured, audit):
    def boom(_args, **_kwargs):
        raise RuntimeError("simulated failure")

    wrapped = tools_mod.safe_handler("pm_boom", boom)
    raw = wrapped({})
    body = json.loads(raw)
    assert body["ok"] is False
    assert body["error"]["code"] == error_code.INTERNAL
    assert body["error"]["details"]["type"] == "RuntimeError"
    ctr = audit.get("pm_boom")
    assert ctr.total == 1
    assert ctr.failure == 1
    assert ctr.success == 0


def test_plugin_error_maps_code(configured, audit):
    def bad(_args, **_kwargs):
        raise PluginError(error_code.FORBIDDEN_ACTION, "nope", details={"x": 1})

    wrapped = tools_mod.safe_handler("pm_forbidden", bad)
    body = json.loads(wrapped({}))
    assert body["ok"] is False
    assert body["error"]["code"] == "FORBIDDEN_ACTION"
    assert body["error"]["details"]["x"] == 1
    assert audit.get("pm_forbidden").failure == 1


def test_validation_does_not_raise(configured):
    raw = configured.pm_list_my_groups({"feishu_user_id": None})
    assert isinstance(raw, str)
    assert json.loads(raw)["ok"] is False


def test_host_facing_handlers_never_raise_attribute(configured):
    # Call with weird kwargs
    for fn in (configured.pm_health, configured.pm_list_my_groups):
        try:
            out = fn({"feishu_user_id": "ou_alice"}, unexpected=True)
        except Exception as exc:  # pragma: no cover
            raise AssertionError(f"handler raised: {exc}") from exc
        assert isinstance(out, str)
        json.loads(out)
