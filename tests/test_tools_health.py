"""Module: pm_health tool."""

from __future__ import annotations

import json


def test_pm_health_success_json(configured):
    raw = configured.pm_health({})
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["data"]["plugin"] == "feishu-pm-plugin"
    assert body["data"]["version"]
    assert body["data"]["status"] == "ok"
    assert body["error"] is None


def test_pm_health_audit_success(configured, audit):
    configured.pm_health({})
    ctr = audit.get("pm_health")
    assert ctr.total == 1
    assert ctr.success == 1
    assert ctr.failure == 0


def test_pm_health_ignores_args(configured):
    raw = configured.pm_health({"extra": 1})
    assert json.loads(raw)["ok"] is True
