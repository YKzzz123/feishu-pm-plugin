"""Business middleware (group resolve + authorize).

This package is NOT Hermes host middleware (ctx.register_middleware).
It is the in-process gate for user × group × action. P1+ may replace the
InMemory implementation with an HTTP client to PM Backend while keeping
the same call semantics.
"""

from __future__ import annotations

from middleware.audit import ToolAudit, ToolCounters
from middleware.errors import PluginError, error_code
from middleware.memory import InMemoryGroupMiddleware
from middleware.types import (
    ACTION_READ_GROUP_CONTEXT,
    ACTIONS_RESERVED_DENY,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    AuthDecision,
    GroupBinding,
)

__all__ = [
    "ACTION_READ_GROUP_CONTEXT",
    "ACTIONS_RESERVED_DENY",
    "AuthDecision",
    "GroupBinding",
    "InMemoryGroupMiddleware",
    "PluginError",
    "ROLE_MEMBER",
    "ROLE_OWNER",
    "ROLE_VIEWER",
    "ToolAudit",
    "ToolCounters",
    "error_code",
]
