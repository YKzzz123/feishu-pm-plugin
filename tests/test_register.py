"""Module: register(ctx) tool registration probe."""

from __future__ import annotations

from typing import Any


class FakeCtx:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def register_tool(self, *args, **kwargs):
        if kwargs.get("name"):
            name = kwargs["name"]
            schema = kwargs.get("schema")
            handler = kwargs.get("handler")
        else:
            name, schema, handler = args[0], args[1], args[2]
        self.tools[name] = {"schema": schema, "handler": handler}


def test_register_exposes_both_tools():
    import importlib

    mod = importlib.import_module("__init__")
    ctx = FakeCtx()
    mod.register(ctx)
    assert set(ctx.tools) == {"pm_health", "pm_list_my_groups"}
    for name, entry in ctx.tools.items():
        assert callable(entry["handler"])
        assert entry["schema"]["name"] == name
