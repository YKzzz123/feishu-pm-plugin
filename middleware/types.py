"""Group binding types and action constants for business middleware."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

ROLE_OWNER: Final = "owner"
ROLE_MEMBER: Final = "member"
ROLE_VIEWER: Final = "viewer"

ACTION_READ_GROUP_CONTEXT: Final = "read_group_context"

# Reserved write/ops action names: known but denied in skeleton matrix.
ACTIONS_RESERVED_DENY: Final[frozenset[str]] = frozenset(
    {
        "upload_drive",
        "manage_members",
        "approve_weekly",
        "write_wiki",
        "request_weekly_summary",
    }
)

# owner + member may read; viewer also read (optional fixture role)
_READ_ROLES: Final[frozenset[str]] = frozenset(
    {ROLE_OWNER, ROLE_MEMBER, ROLE_VIEWER}
)


class AuthDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class GroupBinding:
    group_id: str
    role: str
    name: str | None = None
    code: str | None = None


def role_allows(role: str, action: str) -> bool:
    """Return True if role is granted action under the skeleton matrix."""
    if action == ACTION_READ_GROUP_CONTEXT:
        return role in _READ_ROLES
    # reserved or unknown → not allowed by role matrix
    return False
