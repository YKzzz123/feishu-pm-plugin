"""feishu-pm-plugin — Hermes plugin entry (P0 skeleton)."""

from __future__ import annotations

from typing import Any

from tools import PLUGIN_NAME, PLUGIN_VERSION, register_tools


def register(ctx: Any) -> None:
    """Hermes calls register(ctx) after enable."""
    register_tools(ctx)


__all__ = ["PLUGIN_NAME", "PLUGIN_VERSION", "register"]
