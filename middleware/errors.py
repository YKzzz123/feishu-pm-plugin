"""Stable error codes and PluginError for business paths."""

from __future__ import annotations

from typing import Any


# Stable codes returned in JSON error.code
class error_code:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN_ACTION = "FORBIDDEN_ACTION"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL = "INTERNAL"


class PluginError(Exception):
    """Business/validation error that handlers map to ok:false JSON (not raised to host)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
