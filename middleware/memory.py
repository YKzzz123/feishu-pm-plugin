"""In-memory group middleware for P0 tests and local doctor runs."""

from __future__ import annotations

from middleware.errors import PluginError, error_code
from middleware.types import (
    ACTION_READ_GROUP_CONTEXT,
    AuthDecision,
    GroupBinding,
    role_allows,
)


class InMemoryGroupMiddleware:
    """Fixture-backed resolve_groups + authorize. No network I/O."""

    def __init__(
        self,
        bindings: dict[str, list[GroupBinding]] | None = None,
    ) -> None:
        # feishu_user_id -> bindings
        self._bindings: dict[str, list[GroupBinding]] = {
            uid: list(items) for uid, items in (bindings or {}).items()
        }

    def resolve_groups(self, feishu_user_id: str) -> list[GroupBinding]:
        uid = _require_user_id(feishu_user_id)
        return list(self._bindings.get(uid, []))

    def authorize(
        self, feishu_user_id: str, group_id: str, action: str
    ) -> AuthDecision:
        uid = _require_user_id(feishu_user_id)
        gid = (group_id or "").strip()
        act = (action or "").strip()
        if not gid:
            raise PluginError(
                error_code.VALIDATION_ERROR,
                "group_id is required",
            )
        if not act:
            raise PluginError(
                error_code.VALIDATION_ERROR,
                "action is required",
            )

        binding = next(
            (b for b in self._bindings.get(uid, []) if b.group_id == gid),
            None,
        )
        if binding is None:
            return AuthDecision.DENY

        if role_allows(binding.role, act):
            return AuthDecision.ALLOW
        return AuthDecision.DENY

    def set_bindings(self, feishu_user_id: str, bindings: list[GroupBinding]) -> None:
        """Test/admin helper for fixtures."""
        uid = _require_user_id(feishu_user_id)
        self._bindings[uid] = list(bindings)


def default_fixture_middleware() -> InMemoryGroupMiddleware:
    """Seed AI group + Dev group style fixtures for demos/tests."""
    return InMemoryGroupMiddleware(
        {
            "ou_alice": [
                GroupBinding(
                    group_id="grp_ai",
                    role="owner",
                    name="AI 组",
                    code="ai",
                ),
                GroupBinding(
                    group_id="grp_dev",
                    role="member",
                    name="开发组",
                    code="dev",
                ),
            ],
            "ou_bob": [
                GroupBinding(
                    group_id="grp_dev",
                    role="viewer",
                    name="开发组",
                    code="dev",
                ),
            ],
            "ou_carol": [],  # unbound
        }
    )


def _require_user_id(feishu_user_id: str) -> str:
    if feishu_user_id is None:
        raise PluginError(
            error_code.VALIDATION_ERROR,
            "feishu_user_id is required",
        )
    uid = str(feishu_user_id).strip()
    if not uid:
        raise PluginError(
            error_code.VALIDATION_ERROR,
            "feishu_user_id is required",
        )
    return uid


# Re-export for callers that only need the action name with memory helpers
__all__ = [
    "ACTION_READ_GROUP_CONTEXT",
    "InMemoryGroupMiddleware",
    "default_fixture_middleware",
]
