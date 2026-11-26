"""In-memory log of recent search requests for the Ops tab."""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


class SlowQueryLog:
    """Bounded, thread-safe ring buffer of recent search requests."""

    def __init__(self, capacity: int = 100, threshold_ms: float = 250.0) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=max(1, int(capacity)))
        self._lock = threading.Lock()
        self.threshold_ms = max(0.0, float(threshold_ms))

    def record(
        self,
        *,
        route: str,
        wall_ms: float,
        method: str = "GET",
        q: str | None = None,
        es_took_ms: float | int | None = None,
        total: int | None = None,
        returned: int | None = None,
        status: str = "ok",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "route": route,
            "method": method,
            "q": q,
            "wall_ms": round(float(wall_ms), 2),
            "es_took_ms": es_took_ms,
            "total": total,
            "returned": returned,
            "status": status,
            "slow": float(wall_ms) >= self.threshold_ms,
            "details": details or {},
        }
        with self._lock:
            self._entries.appendleft(entry)
        return entry

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            entries = list(self._entries)
        return {
            "threshold_ms": self.threshold_ms,
            "capacity": self._entries.maxlen,
            "count": len(entries),
            "slow_count": sum(1 for entry in entries if entry["slow"]),
            "entries": entries,
        }
