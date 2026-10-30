"""In-process tool invocation audit (total / success / failure).

P0: memory only. P1+ may export the same counters to Backend/operations.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCounters:
    total: int = 0
    success: int = 0
    failure: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "success": self.success,
            "failure": self.failure,
        }


@dataclass
class ToolAudit:
    """Thread-safe per-tool counters."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _by_tool: dict[str, ToolCounters] = field(default_factory=dict)

    def record(self, tool_name: str, *, success: bool) -> None:
        name = (tool_name or "").strip() or "_unknown"
        with self._lock:
            ctr = self._by_tool.setdefault(name, ToolCounters())
            ctr.total += 1
            if success:
                ctr.success += 1
            else:
                ctr.failure += 1

    def get(self, tool_name: str) -> ToolCounters:
        name = (tool_name or "").strip() or "_unknown"
        with self._lock:
            ctr = self._by_tool.get(name)
            if ctr is None:
                return ToolCounters()
            return ToolCounters(
                total=ctr.total, success=ctr.success, failure=ctr.failure
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tools": {
                    name: ctr.to_dict() for name, ctr in sorted(self._by_tool.items())
                }
            }

    def reset(self) -> None:
        """Test helper: clear all counters."""
        with self._lock:
            self._by_tool.clear()
