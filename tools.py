"""Tool handlers: always return JSON str; never raise to Hermes."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from middleware.audit import ToolAudit
from middleware.errors import PluginError, error_code
from middleware.memory import InMemoryGroupMiddleware, default_fixture_middleware
from middleware.types import ACTION_READ_GROUP_CONTEXT, AuthDecision
from schemas import PM_HEALTH_SCHEMA, PM_LIST_MY_GROUPS_SCHEMA

logger = logging.getLogger(__name__)

PLUGIN_NAME = "feishu-pm-plugin"
PLUGIN_VERSION = "0.1.0"

# Process-level defaults (register() may replace for tests)
_audit = ToolAudit()
_middleware: InMemoryGroupMiddleware = default_fixture_middleware()


def get_audit() -> ToolAudit:
    return _audit


def get_middleware() -> InMemoryGroupMiddleware:
    return _middleware


def configure(
    *,
    middleware: InMemoryGroupMiddleware | None = None,
    audit: ToolAudit | None = None,
) -> None:
    """Test/setup hook to inject middleware and audit instances."""
    global _middleware, _audit
    if middleware is not None:
        _middleware = middleware
    if audit is not None:
        _audit = audit


def _envelope(
    *,
    ok: bool,
    data: Any = None,
    error: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {"ok": ok, "data": data, "error": error},
        ensure_ascii=False,
    )


def safe_handler(
    tool_name: str,
    fn: Callable[..., dict[str, Any]],
) -> Callable[..., str]:
    """Wrap a tool body so the host always receives a JSON str and never an exception."""

    def _wrapped(args: dict | None = None, **kwargs: Any) -> str:
        success = False
        try:
            payload = fn(args or {}, **kwargs)
            if not isinstance(payload, dict):
                raise PluginError(
                    error_code.INTERNAL,
                    "handler must return a dict payload",
                )
            ok = bool(payload.get("ok", False))
            body = _envelope(
                ok=ok,
                data=payload.get("data"),
                error=payload.get("error"),
            )
            success = ok
            return body
        except PluginError as exc:
            success = False
            return _envelope(
                ok=False,
                data=None,
                error={
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
        except Exception as exc:  # noqa: BLE001 — must not leak to host
            logger.exception("tool %s failed", tool_name)
            success = False
            return _envelope(
                ok=False,
                data=None,
                error={
                    "code": error_code.INTERNAL,
                    "message": "internal error",
                    "details": {"type": type(exc).__name__},
                },
            )
        finally:
            try:
                _audit.record(tool_name, success=success)
            except Exception:  # noqa: BLE001
                logger.exception("audit record failed for %s", tool_name)

    return _wrapped


def _pm_health_impl(_args: dict, **_kwargs: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "status": "ok",
            "plugin": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
        },
        "error": None,
    }


def _pm_list_my_groups_impl(args: dict, **_kwargs: Any) -> dict[str, Any]:
    raw = args.get("feishu_user_id")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise PluginError(
            error_code.VALIDATION_ERROR,
            "feishu_user_id is required",
        )
    uid = str(raw).strip()

    bindings = _middleware.resolve_groups(uid)
    visible: list[dict[str, Any]] = []
    for b in bindings:
        decision = _middleware.authorize(
            uid, b.group_id, ACTION_READ_GROUP_CONTEXT
        )
        if decision is AuthDecision.ALLOW:
            visible.append(
                {
                    "group_id": b.group_id,
                    "role": b.role,
                    "name": b.name,
                    "code": b.code,
                }
            )

    return {
        "ok": True,
        "data": {
            "feishu_user_id": uid,
            "groups": visible,
            "count": len(visible),
        },
        "error": None,
    }


pm_health = safe_handler("pm_health", _pm_health_impl)
pm_list_my_groups = safe_handler("pm_list_my_groups", _pm_list_my_groups_impl)


def register_tools(ctx: Any) -> None:
    """Register tools on a Hermes plugin context."""
    specs = [
        (PM_HEALTH_SCHEMA, pm_health),
        (PM_LIST_MY_GROUPS_SCHEMA, pm_list_my_groups),
    ]
    for schema, handler in specs:
        name = schema["name"]
        try:
            ctx.register_tool(
                name=name,
                schema=schema,
                handler=handler,
                toolset="feishu_pm",
            )
        except TypeError:
            # Older/newer hermes may use positional or different kwargs
            ctx.register_tool(name, schema, handler)
