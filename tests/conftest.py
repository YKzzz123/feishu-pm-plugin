"""Shared fixtures: isolated middleware + audit per test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root on path for `import middleware`, `import tools`, etc.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from middleware.audit import ToolAudit  # noqa: E402
from middleware.memory import InMemoryGroupMiddleware, default_fixture_middleware  # noqa: E402
from middleware.types import GroupBinding  # noqa: E402
import tools as tools_mod  # noqa: E402


@pytest.fixture
def audit() -> ToolAudit:
    a = ToolAudit()
    return a


@pytest.fixture
def middleware() -> InMemoryGroupMiddleware:
    return default_fixture_middleware()


@pytest.fixture
def configured(middleware: InMemoryGroupMiddleware, audit: ToolAudit):
    tools_mod.configure(middleware=middleware, audit=audit)
    yield tools_mod
    # reset to defaults so tests don't leak
    tools_mod.configure(
        middleware=default_fixture_middleware(),
        audit=ToolAudit(),
    )


@pytest.fixture
def custom_middleware() -> InMemoryGroupMiddleware:
    """Alice owns AI; Bob member on AI with no read stripped via role edge cases."""
    mw = InMemoryGroupMiddleware(
        {
            "ou_alice": [
                GroupBinding("grp_ai", "owner", name="AI 组", code="ai"),
                GroupBinding("grp_dev", "member", name="开发组", code="dev"),
            ],
            "ou_denied": [
                # unknown role → cannot read_group_context
                GroupBinding("grp_ai", "guest", name="AI 组", code="ai"),
            ],
        }
    )
    return mw
