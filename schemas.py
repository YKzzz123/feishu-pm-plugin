"""LLM-visible tool schemas for feishu-pm-plugin (P0)."""

from __future__ import annotations

from typing import Any

PM_HEALTH_SCHEMA: dict[str, Any] = {
    "name": "pm_health",
    "description": (
        "Health check for the feishu-pm-plugin. "
        "Returns whether the plugin is loaded. No Feishu writes."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}

PM_LIST_MY_GROUPS_SCHEMA: dict[str, Any] = {
    "name": "pm_list_my_groups",
    "description": (
        "List groups the given Feishu user can access (read_group_context). "
        "Uses business group middleware. Skeleton: pass feishu_user_id explicitly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "feishu_user_id": {
                "type": "string",
                "description": (
                    "Feishu user id for this call (skeleton). "
                    "Production should inject trusted open_id from the gateway."
                ),
            },
        },
        "required": ["feishu_user_id"],
        "additionalProperties": False,
    },
}

ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    PM_HEALTH_SCHEMA,
    PM_LIST_MY_GROUPS_SCHEMA,
]
