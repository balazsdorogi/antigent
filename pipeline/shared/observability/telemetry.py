"""Tier 1 — system telemetry: tool latency, exit codes, (later) memory.

Persists structured JSONL through the run's storage handle and echoes a concise
event to the console for live development visibility.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import structlog

from pipeline.shared.observability._ids import utcnow_iso
from pipeline.shared.storage import RunHandle


@dataclass
class ToolRunMetrics:
    """Mutable metrics a caller fills in during a :meth:`TelemetrySink.tool_run`."""

    exit_code: int | None = None
    # Container memory is not reliably observable from the host on Docker Desktop
    # (containers run in a VM); populated from cgroup stats in the AWS iteration.
    max_rss_kb: int | None = None


class TelemetrySink:
    """Append-only telemetry stream for one run."""

    def __init__(self, handle: RunHandle, *, stream: str = "telemetry.jsonl") -> None:
        self._handle = handle
        self._stream = stream
        self._log = structlog.get_logger("antigent.telemetry")

    def event(self, event: str, **fields: Any) -> None:
        """Record one telemetry event (persisted + echoed)."""
        record = {"ts": utcnow_iso(), "tier": "telemetry", "event": event, **fields}
        self._handle.append_jsonl(self._stream, record)
        self._log.info(event, **fields)

    @contextmanager
    def tool_run(self, tool: str, *, image: str) -> Iterator[ToolRunMetrics]:
        """Time a tool invocation, recording start/end (+ error) events."""
        metrics = ToolRunMetrics()
        self.event("tool_start", tool=tool, image=image)
        start = time.monotonic()
        try:
            yield metrics
        except BaseException as exc:
            self.event("tool_error", tool=tool, error=type(exc).__name__)
            raise
        finally:
            self.event(
                "tool_end",
                tool=tool,
                image=image,
                exit_code=metrics.exit_code,
                duration_s=round(time.monotonic() - start, 3),
                max_rss_kb=metrics.max_rss_kb,
            )
