"""Module: InMemoryGroupMiddleware resolve + authorize."""

from __future__ import annotations

import pytest

from middleware.errors import PluginError
from middleware.memory import InMemoryGroupMiddleware, default_fixture_middleware
from middleware.types import (
    ACTION_READ_GROUP_CONTEXT,
    AuthDecision,
    GroupBinding,
)


def test_user_bound_to_multiple_groups():
    mw = default_fixture_middleware()
    groups = mw.resolve_groups("ou_alice")
    ids = {b.group_id for b in groups}
    assert ids == {"grp_ai", "grp_dev"}
    assert len(groups) == 2


def test_user_bound_to_zero_groups():
    mw = default_fixture_middleware()
    assert mw.resolve_groups("ou_carol") == []


def test_unknown_user_returns_empty_not_others():
    mw = default_fixture_middleware()
    assert mw.resolve_groups("ou_nobody") == []


def test_empty_identity_rejected():
    mw = default_fixture_middleware()
    with pytest.raises(PluginError) as ei:
        mw.resolve_groups("")
    assert ei.value.code == "VALIDATION_ERROR"
    with pytest.raises(PluginError):
        mw.resolve_groups("   ")


def test_authorize_member_read_allowed():
    mw = default_fixture_middleware()
    assert (
        mw.authorize("ou_alice", "grp_dev", ACTION_READ_GROUP_CONTEXT)
        is AuthDecision.ALLOW
    )


def test_authorize_owner_read_allowed():
    mw = default_fixture_middleware()
    assert (
        mw.authorize("ou_alice", "grp_ai", ACTION_READ_GROUP_CONTEXT)
        is AuthDecision.ALLOW
    )


def test_authorize_unbound_denied():
    mw = default_fixture_middleware()
    assert (
        mw.authorize("ou_bob", "grp_ai", ACTION_READ_GROUP_CONTEXT)
        is AuthDecision.DENY
    )


def test_authorize_unknown_action_denied():
    mw = default_fixture_middleware()
    assert mw.authorize("ou_alice", "grp_ai", "not_a_real_action") is AuthDecision.DENY
    assert mw.authorize("ou_alice", "grp_ai", "upload_drive") is AuthDecision.DENY


def test_authorize_role_without_permission_denied():
    mw = InMemoryGroupMiddleware(
        {"ou_x": [GroupBinding("grp_ai", "guest", name="AI")]}
    )
    assert (
        mw.authorize("ou_x", "grp_ai", ACTION_READ_GROUP_CONTEXT) is AuthDecision.DENY
    )


def test_no_cross_user_leakage():
    mw = default_fixture_middleware()
    bob = {b.group_id for b in mw.resolve_groups("ou_bob")}
    alice = {b.group_id for b in mw.resolve_groups("ou_alice")}
    assert "grp_ai" in alice
    assert "grp_ai" not in bob
