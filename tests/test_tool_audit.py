"""Module: ToolAudit counters and snapshot."""

from __future__ import annotations

import json

from middleware.audit import ToolAudit
import tools as tools_mod


def test_audit_accumulates_success_and_failure(configured, audit):
    configured.pm_health({})
    configured.pm_health({})
    configured.pm_list_my_groups({})  # fail validation
    configured.pm_list_my_groups({"feishu_user_id": "ou_alice"})

    h = audit.get("pm_health")
    assert h.total == 2 and h.success == 2 and h.failure == 0

    g = audit.get("pm_list_my_groups")
    assert g.total == 2 and g.success == 1 and g.failure == 1


def test_snapshot_structure(configured, audit):
    configured.pm_health({})
    snap = audit.snapshot()
    assert "tools" in snap
    assert snap["tools"]["pm_health"]["success"] == 1


def test_unknown_tool_get_returns_zeros():
    a = ToolAudit()
    c = a.get("never_called")
    assert c.total == c.success == c.failure == 0


def test_reset(audit):
    audit.record("x", success=True)
    audit.reset()
    assert audit.snapshot()["tools"] == {}


def test_snapshot_does_not_raise(configured, audit):
    configured.pm_health({})
    assert isinstance(audit.snapshot(), dict)
